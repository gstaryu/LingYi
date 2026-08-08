# 系统架构

本文档描述灵医（LingYi）的整体架构、分层设计、依赖注入与状态流转。

## 总体架构

灵医采用 **分层 + Agent 编排** 架构：核心层（Agent / RAG / Safety / Storage / Knowledge）不依赖任何 Web 框架；API 层在 `lifespan` 中组装实例并存入 `app.state`；前端通过 REST + SSE 消费。

```
┌─────────────────────────────────────────────┐
│  前端 (Next.js + React)                       │
│  ChatWindow / ConsultationTimeline / 画像     │
└───────────────┬─────────────────────────────┘
                │ REST + SSE / WebSocket
┌───────────────▼─────────────────────────────┐
│  API 层 (FastAPI)                             │
│  routes: auth / chat / threads / profiles / upload │
│  lifespan 组装实例 -> app.state，请求级 Depends 注入 │
└───────────────┬─────────────────────────────┘
                │ 调用
┌───────────────▼─────────────────────────────┐
│  Agent 层 (LangGraph)                         │
│  graph.py (workflow) / graph_multiagent.py    │
│  skills + specialists + memory + safety       │
└──┬────────┬────────┬────────┬────────┬──────┘
   │        │        │        │        │
┌──▼──┐ ┌──▼──┐ ┌───▼───┐ ┌─▼──┐ ┌──▼─────┐
│ RAG │ │Tools│ │Safety │ │MCP │ │Storage │
│混合检索│ │7工具│ │十八反│ │服务端│ │SQLite │
└─────┘ └────┘ └───────┘ └────┘ └────────┘
```

## 分层与依赖规则

| 层 | 职责 | 依赖规则 |
|---|---|---|
| **Core**（agent / rag / safety / storage / knowledge / tools / parsers） | 领域逻辑 | 构造函数注入，**不 import FastAPI / Streamlit** |
| **API**（lingyi/api） | HTTP 接口、鉴权、流式 | 实例在 `lifespan` 创建存 `app.state`；请求级 `Depends` 读取；`deps.py` 无模块级全局单例 |
| **UI**（frontend） | 用户交互 | 通过 `lib/api.ts` 调后端 |

> 这条规则保证 Core 层可独立单测（注入桩），不耦合 Web 框架。

## 依赖注入

```python
# lingyi/api/app.py lifespan
app.state.agent, app.state.profile_writer = create_multiagent_agent(
    llm, rag_client, storage, safety_engine, checkpointer, tools, ...
)

# lingyi/api/routes/chat.py
async def chat(req, agent = Depends(get_agent), user = Depends(get_current_user)):
    ...
```

- `get_agent` / `get_current_user` 等 Depends 函数从 `app.state` / JWT 读取。
- 测试用 `app.dependency_overrides` 注入桩，不靠环境变量分支。

## AgentState

LangGraph 状态（`lingyi/agent/state.py`）核心字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `messages` | `list[BaseMessage]` | 对话历史（`add_messages` reducer，支持 `RemoveMessage` 按 ID 删） |
| `symptoms` | `list[str]` | 提取的症状 |
| `intent_type` | `str` | chat / consult / diagnose / safety_rejected |
| `diagnosis` | `str` | 辨证结论 |
| `treatment_plan` | `str` | 处方建议（含 `herb_names` JSON 块） |
| `patient_profile` | `dict` | 加载的画像（体质/过敏/既往） |
| `consultation_notes` | `list` | 专家会诊笔记（`operator.add` 归约；`None` 触发重置） |
| `safety_errors` | `str` | 安全校验失败反馈 |
| `reviewer_approved` | `bool` | 对抗审查结论 |
| `has_provided_treatment` | `bool` | 是否已出过方 |

## 双工作流模式

通过 `AGENT_MODE` 切换，`lifespan` 选择图工厂：

- **workflow**（`graph.py`）：固定链路 `inquiry -> rag_search -> diagnosis -> treatment -> safety_check`。
- **multiagent**（`graph_multiagent.py`）：`dispatch_specialists` 用 `Send` 并行扇出到三专家，`synthesis` 汇总，`reviewer` 对抗审查，`safety_check` 硬校验。

两模式共享前置节点（reader / mem_recall / safety_guard / inquiry）与后置节点（summarize / writer）。

## 持久化

- **业务库** `storage/patient_profiles.db`：用户、画像、线程、本草、方剂、禁忌（SQLiteStorage，aiosqlite 异步）。
- **检查点库** `storage/checkpoints.db`：LangGraph `AsyncSqliteSaver`，按 `thread_id` 存对话状态，支持中断恢复。
- 两库分离，避免业务表与检查点表耦合。

## 配置

`lingyi/config.py` 用 `pydantic-settings` 从环境变量 / `.env` 加载，`get_settings()` 返回单例。完整配置项见 [deployment.md](deployment.md)。

## 日志与追踪

- 所有模块 `logger = logging.getLogger(__name__)`，`lingyi/logging.py` 统一配置（UTF-8 强制，避免 Windows 控制台乱码）。
- `ENABLE_TRACING=true` 时 `lingyi/tracing.py` 配置 LangSmith 链路追踪。
