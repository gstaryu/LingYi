# Agent 工作流

## 概述

灵医的 Agent 层基于 LangGraph StateGraph 编排，支持两种工作流模式，通过 `AGENT_MODE` 环境变量切换：

| 模式 | 配置值 | 图工厂 | 说明 |
|---|---|---|---|
| 单 Agent 工作流 | `workflow`（默认） | `lingyi/agent/graph.py: create_agent` | 固定的 diagnosis -> treatment 链 |
| 多智能体会诊 | `multiagent` | `lingyi/agent/graph_multiagent.py: create_multiagent_agent` | 并行专家会诊 + 综合合成 |

`lingyi/api/app.py` 的 `lifespan` 根据 `settings.agent_mode` 选择图工厂，编译后的 StateGraph 存入 `app.state.agent`，请求级通过 `Depends(get_agent)` 注入。

## 状态定义

Agent 状态由 `lingyi/agent/state.py: AgentState`（TypedDict, total=False）定义，所有节点共享：

| 字段 | 类型 | Reducer | 说明 |
|---|---|---|---|
| `messages` | `list[BaseMessage]` | `add_messages` | 对话历史（自动合并/按 ID 删除） |
| `consultation_notes` | `list[dict]` | `_consultation_notes_reducer` | 会诊笔记（None 重置 / list 追加） |
| `symptoms` | `list[str]` | - | 结构化症状清单 |
| `intent_type` | `str` | - | 意图: chat / consult / diagnose / safety_rejected |
| `diagnosis` | `Optional[str]` | - | 辨证结论 |
| `treatment_plan` | `Optional[str]` | - | 处方建议 |
| `patient_profile` | `dict` | - | 患者长期画像 |
| `safety_errors` | `Optional[str]` | - | 安全校验错误 |
| `reviewer_approved` | `bool` | - | 对抗审查者是否批准 |
| `synthesis_message_id` | `Optional[str]` | - | 综合消息 ID（重试时 RemoveMessage） |
| `inquiry_count` | `int` | - | 问诊轮次计数 |
| `has_provided_treatment` | `bool` | - | 是否已开方 |

`_consultation_notes_reducer` 归约器：收到 `None` 时重置为空列表（每次新 diagnose 流程开始时由 `dispatch_specialists` 触发），收到 `list` 时追加（专家节点并行返回 `[note]`，通过多次归约累积）。

## Workflow 模式（默认）

```
START -> reader -> mem_recall -> safety_guard -> inquiry -> 路由
                                                        ├─ "chat/consult" -> summarize_condition -> writer -> END
                                                        ├─ "diagnose" -> rag_search -> diagnosis -> treatment -> summarize_condition -> writer -> END
                                                        └─ "safety_rejected" -> summarize_condition -> writer -> END
```

### 节点说明

| 节点 | 技能类 | 职责 |
|---|---|---|
| `reader` | `ReaderSkill` | 解析用户上传的文件（PDF/DOCX/TXT），提取纯文本 |
| `mem_recall` | `MemRecallSkill` | 从存储加载患者画像（体质/过敏/既往史） |
| `safety_guard` | `SafetyGuardSkill` | 前置安全拦截，关键词预检 + LLM 审查 |
| `inquiry` | `InquirySkill` | 意图识别 + 症状提取 + 问诊控制 |
| `rag_search` | `RAGSearchSkill` | RAG 知识检索（向量 + BM25 混合） |
| `rag_grader` | `RAGGraderSkill` | RAG 质量评估（可选，`RAG_ENABLE_EVALUATION=true` 时启用） |
| `rag_rewrite` | `RAGRewriteSkill` | 查询重写重试 |
| `diagnosis` | `DiagnosisSkill` | 辨证分析 |
| `treatment` | `TreatmentSkill` | 处方生成 + SafetyEngine 安全校验 |
| `summarize_condition` | 路由节点 | 判断是否需要上下文压缩 |
| `summarize_and_write` | `SummarizerSkill` | 用 `RemoveMessage` 压缩历史 |
| `writer` | `ProfileWriterSkill` | 后台写入患者画像 |

### 路由逻辑

**safety_guard 路由** (`_safety_guard_router`)：
- `intent_type == "safety_rejected"` -> `summarize_condition`
- 其他 -> `inquiry`

**inquiry 主路由** (`_master_router`)：
- `intent in ("consult", "inquiry_more")` -> `END`（暂停返回追问）
- `intent == "diagnose"` -> RAG 决策逻辑 (`rag_decision_logic`)
  - 有症状 -> `rag_search`
  - 无症状 -> `diagnosis`
- 其他 -> `END`

**RAG 评估环路**（`RAG_ENABLE_EVALUATION=true` 时）：
```
rag_search -> rag_grader -> (score >= 0.7 或重试耗尽 -> diagnosis | 否则 -> rag_rewrite -> rag_search)
```

**treatment 安全校验路由** (`safety_check_logic`)：
- 不通过且未超限 -> `re_treatment`（回 treatment 重写）
- 通过或耗尽 -> `safe_to_end`（-> `summarize_condition`）

## 多智能体模式（multiagent）

```
START -> reader -> mem_recall -> safety_guard -> inquiry -> 路由
                                                        ├─ "chat/consult" -> summarize_condition -> writer -> END
                                                        └─ "diagnose" -> dispatch_specialists
                                                                          ├─ Send -> specialist_bianzheng ─┐
                                                                          ├─ Send -> specialist_fangji ────┤
                                                                          └─ Send -> specialist_bencao ────┘
                                                                              -> synthesis -> reviewer -> safety_check
                                                                              -> summarize_condition -> writer -> END
```

多智能体模式复用 workflow 图的前置节点（reader/mem_recall/safety_guard/inquiry）和后置节点（summarize/writer），替换诊断-处方段为并行专家会诊 + 综合合成。

### 专家节点

专家位于 `lingyi/agent/specialists/`，继承 `SpecialistBase`（`lingyi/agent/specialists/base.py`）：

| 专家 | 文件 | 工具子集 |
|---|---|---|
| 辨证专家 | `bianzheng.py` | `search_tcm_classics`, `get_patient_profile` |
| 方剂专家 | `fangji.py` | `search_formulas`, `lookup_herb`, `search_tcm_classics` |
| 本草专家 | `bencao.py` | `lookup_herb`, `check_herb_safety`, `web_search` |

**架构特点**：
- 每个专家在 `node()` 中做**恰好一次** `chat_model.ainvoke`（非 ReAct 循环）
- 子类可覆写 `prefetch()`，在 LLM 调用前**直接**调用工具（不经过 LLM），将结果拼入 prompt
- 节点返回 `{"consultation_notes": [note]}`，不修改 `messages`（避免并行 reducer 冲突）
- JSON 解析带 fallback（直接 JSON / 代码块 / 嵌入 JSON），保证结构稳定
- 依赖注入：`chat_model` 通过构造函数注入，生产用 `ChatOpenAI`，测试用 `StubChatModel`

### 并行扇出（Send）

`dispatch_specialists` 节点首先重置会诊专用状态（`consultation_notes` -> None, `synthesis_message_id` -> None, 重试计数归零），然后通过 `_fan_out_specialists` 条件边用 `langgraph.types.Send` 并行扇出到三个专家：

```python
[
    Send("specialist_bianzheng", state),
    Send("specialist_fangji", state),
    Send("specialist_bencao", state),
]
```

每个专家获得完整状态副本，返回的 `consultation_notes` 通过 `_consultation_notes_reducer` 归约器拼接。LangGraph 屏障机制确保所有专家完成后才执行 `synthesis`。

### 阶段进度事件

多智能体图通过 `_wrap_with_stage()` 包装节点，在执行前后向 LangGraph 自定义流发送阶段进度事件：

```python
{"type": "stage", "stage": "bianzheng", "label": "辨证", "status": "start"|"done"}
```

阶段标签映射（`STAGE_LABELS`）：问诊 / 辨证 / 方剂 / 本草 / 综合 / 安全审查 / 安全校验。前端会诊时间线据此点亮对应阶段。

### 综合节点（synthesis）

`_make_synthesis_node` 工厂创建综合节点，读取 `consultation_notes` + `symptoms` + `profile` + `safety_errors`，调用 LLM 生成 `diagnosis` + `treatment_plan`。

**输出格式**（prose 格式，流式 token 用户实时可见）：
```
【辨证结论】
（辨证分析段落）

【处方建议】
（治法与处方说明，每味药材标注剂量）
```json
{"herb_names": ["人参", "白术", ...]}
```

孕妇、哺乳期女性使用前需咨询专业中医师
```

**重试机制**：当 reviewer 或 safety_check 拒绝后回 synthesis，state 中已有上一版的 `synthesis_message_id`。综合节点先用 `RemoveMessage(id=prev_id)` 移除旧处方消息，再追加新版，确保历史中只保留最终批准的处方。

### 对抗审查者（reviewer）

`lingyi/agent/safety_reviewer.py: SafetyReviewerAgent` 继承 `SpecialistBase`，在确定性 SafetyEngine 硬校验之前提供智能审查层。

**工作流程**：
1. 从 `treatment_plan` 提取药材列表
2. 直接调用 `check_herb_safety` 工具（确定性规则引擎，无 LLM）
3. 单次 `chat_model.ainvoke` 做审查判断
4. 解析审查结果为 `SafetyReviewResult`（approved / issues / suggestions）

**审查者路由** (`reviewer_router`)：

| 条件 | 路由 | 说明 |
|---|---|---|
| `reviewer_approved == True` | `safety_check` | 审查通过，交由硬校验 |
| `reviewer_approved == False` 且 `retry_count < max_retries` | `synthesis` | 回退重生成 |
| `reviewer_approved == False` 且重试耗尽 | `safety_check` | 交由 SafetyEngine 最终裁决 |

审查者失败时 fail-open（返回 `reviewer_approved=True`），交由确定性 safety_check 裁决。

### 安全校验节点（safety_check）

`_make_safety_check_node` 从 `treatment_plan` 提取药材，用 `SafetyEngine.check_prescription(herbs)` 校验配伍禁忌。不通过则设置 `safety_errors` + 递增 `safety_retry_count`，通过则清除错误。

**safety_check 路由**（复用 `safety_check_logic`）：
- 不通过且未超限 -> `synthesis`（回退重生成，携带错误反馈）
- 通过或耗尽 -> `summarize_condition`

### 双重防御

多智能体模式采用双重安全防御：
1. **智能审查层**（`reviewer`）：`SafetyReviewerAgent`，LLM 驱动的对抗性批评者
2. **确定性硬校验**（`safety_check`）：`SafetyEngine`，十八反/十九畏规则引擎

SafetyEngine 为最终裁决者。两层独立计数（`reviewer_retry_count` 与 `safety_retry_count`），互不干扰。

## 安全机制

### SafetyGuardSkill（前置拦截）

`lingyi/agent/skills/safety_guard.py`，位于 `safety_guard` 节点：
- 关键词预检：检测用户输入中的配伍禁忌意图
- LLM 审查：判断是否涉及危险用药请求
- 拦截后 `intent_type` 设为 `"safety_rejected"`，图直接跳到 `summarize_condition`

**SAFETY_FAIL_MODE**：前置安全审查 LLM 异常时的失败策略：
- `closed`（默认）：异常时拒绝请求
- `open`：异常时放行（交由后续节点处理）

### SafetyEngine（确定性硬校验）

`lingyi/safety/rules.py`，规则引擎，不依赖 LLM：
- 十八反：6 条配伍禁忌规则
- 十九畏：12 条配伍禁忌规则
- `check_prescription(herb_list)` 返回 `(is_safe, error_msg)`
- 在 `treatment` 节点（workflow）/ `safety_check` 节点（multiagent）自动校验

## 记忆系统

### MemRecallSkill（画像加载）

`lingyi/agent/memory/recall.py`，位于 `mem_recall` 节点：
- 每轮重载患者画像（DB 单行 PK 查询廉价）
- 保证后台写入的最终可见性
- 加载 `patient_profile`（体质/过敏/既往史）到 state

### ProfileWriterSkill（画像写入）

`lingyi/agent/memory/profile_writer.py`，位于 `writer` 节点：
- 会诊结束后用 LLM 从对话历史提取体质和过敏史
- **fire-and-forget**：`asyncio.create_task` 后台调度，立即返回不阻塞响应
- 任务存入 `_pending` 集合防 GC，应用关闭时由 `flush()` 统一等待避免丢写
- 提取超时 25 秒（`DEFAULT_EXTRACT_TIMEOUT`），超时跳过本次写入
- 过敏原支持新增和移除（LLM 提取 + 确定性规则兜底）

### SummarizerSkill（上下文压缩）

`lingyi/agent/memory/summarizer.py`，位于 `summarize_and_write` 节点：
- 用 `RemoveMessage(id=...)` 按 ID 真实移除旧消息
- 触发阈值：`token_compression_threshold`（默认 8000 字符）
- `should_summarize(state, threshold)` 判断是否需要压缩

## 问诊技能（InquirySkill）

`lingyi/agent/skills/inquiry.py`，位于 `inquiry` 节点：

### 结构化输出

使用 `with_structured_output(InquiryResult)` 强制 LLM 返回结构化数据：

| 字段 | 类型 | 说明 |
|---|---|---|
| `intent_type` | `str` | chat / consult / diagnose |
| `is_complete` | `bool` | 信息是否足够辨证 |
| `symptoms` | `list[str]` | 结构化症状 |
| `response` | `str` | 回复（chat=闲聊, consult=追问, diagnose=留空） |

结构化输出不可用时回退 JSON 解析，降级为 `consult`（继续问诊）而非 `chat`（直接结束）。

### 问诊循环控制

- `max_followups`（默认 1）：达到上限后强制返回 `intent="diagnose"`
- 仅在初始诊断阶段（尚未提供治疗）应用追问上限
- 已提供治疗后，用户的调整请求需正常分类重新进入诊断
- `consult` 意图时递增 `inquiry_count`，`diagnose` 时不生成追问消息

### 已开方时的处方注入

当 `has_provided_treatment == True` 时，注入当前处方药材和辨证结论，供 LLM 判断是否需要调整处方。同时确定性检测用户新报告的过敏原，即时注入 `patient_profile`。

### 感谢词检测

检测到感谢词（谢谢/感谢/多谢/thanks）时降级为 `chat`，不触发辨证。

## 工具层

`lingyi/tools/factory.py: create_tools()` 通过依赖注入构造领域工具集。工具以闭包形式捕获注入的 `rag_client` / `storage` / `safety_engine`，不持有模块级全局单例。

| # | 工具名 | 说明 | 参数 |
|---|---|---|---|
| 1 | `search_tcm_classics` | 检索中医经典古籍 | `query: str` |
| 2 | `lookup_herb` | 查询本草信息 | `name: str` |
| 3 | `search_formulas` | 搜索方剂 | `query: str` |
| 4 | `check_herb_safety` | 校验配伍禁忌 | `herbs: list[str]` |
| 5 | `get_patient_profile` | 获取患者画像 | `patient_id: str` |
| 6 | `save_patient_profile` | 保存/更新画像 | `patient_id, constitution?, allergies?` |
| 7 | `web_search` | 网络搜索（可选） | `query: str` |

`web_search` 工具有状态（MCP 子进程），由 `build_web_search_tool` 异步构建后注入。为 None 时省略，Agent 仍可运行。

### 设计原则：工具 vs 图边

| 类别 | 含义 | 示例 |
|---|---|---|
| **工具** | Agent 可选择做的事（LLM 自主决定） | search_tcm_classics, lookup_herb, web_search |
| **图边** | 必须永远发生的事（不可跳过） | safety_guard, SafetyEngine, summarizer, reader, profile_writer |

安全校验、上下文压缩、画像写入等关键操作留在图边，不放给 Agent 自行决定。

## MCP 服务端

`lingyi/mcp/server.py` 使用 FastMCP (stdio) 暴露 5 个只读工具，供 Claude Desktop 等外部客户端调用：

| 工具名 | 说明 |
|---|---|
| `search_tcm_classics` | 检索中医经典古籍 |
| `lookup_herb` | 查询本草信息 |
| `search_formulas` | 搜索方剂 |
| `check_herb_safety` | 校验配伍禁忌 |
| `get_patient_profile` | 获取患者画像 |

**安全设计**：仅暴露查询/校验类工具，不暴露 `save_patient_profile`（避免外部客户端写库风险）。

**依赖注入**：通过模块级 `_deps` 持有者 + `configure()` 函数，生产由 `app_lifespan` 初始化，测试直接 `configure(...)` 注入桩。

启动命令：
```bash
python -m lingyi.mcp.server
```

## 模型配置

多智能体模式支持按角色配置独立模型：

| 角色 | 配置项 | 默认值 |
|---|---|---|
| 默认 | `MODEL_NAME` | `qwen-max` |
| 辨证专家 | `MODEL_NAME_BIANZHENG` | 留空回退到 `MODEL_NAME` |
| 方剂专家 | `MODEL_NAME_FANGJI` | 留空回退到 `MODEL_NAME` |
| 本草专家 | `MODEL_NAME_BENCAO` | 留空回退到 `MODEL_NAME` |

专家角色的 LLM 重试次数使用 `LLM_SPECIALIST_MAX_RETRIES`（默认 1），低于 `LLM_MAX_RETRIES`（默认 3），避免网关抖动时静默重试风暴拖慢会诊。
