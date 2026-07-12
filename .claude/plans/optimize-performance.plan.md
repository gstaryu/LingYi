# Plan: 灵医项目性能优化与 LangChain/LangGraph 规范化

**Source**: 用户需求 + 代码全面审查
**Complexity**: Large
**Estimated effort**: 5 个阶段，17 个任务

## Summary

项目存在三类核心问题：
1. **性能问题** — LLM 无超时、无流式输出、SQLite 连接反复创建、无重试机制
2. **LangChain/LangGraph 使用不规范** — 自定义封装绕过内置功能、未用流式 API、checkpointer 创建方式错误
3. **其他 Bug** — .env 变量名不匹配、重复代码、reranker 未集成、writer 任务丢失

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| LLM 调用 | ChatOpenAI 文档 | `timeout=30, max_retries=3` 构造函数参数 |
| 流式输出 | LangGraph 文档 | `graph.astream(input, stream_mode="messages")` |
| Checkpointer | LangGraph 文档 | `AsyncSqliteSaver.from_conn_string(path)` |
| JSON 解析 | LangChain | 公共 `parse_json_response()` 工具函数 |
| 消息格式 | LangChain | `list[BaseMessage]` 而非 `list[dict]` |

## Files to Change

| File | Action | Why |
|---|---|---|
| `lingyi/config.py` | UPDATE | 添加 llm_timeout/llm_max_retries 配置 |
| `lingyi/models/dashscope.py` | UPDATE | ChatOpenAI 传入 timeout/max_retries |
| `lingyi/models/base.py` | UPDATE | ainvoke 统一接收 list[BaseMessage] |
| `lingyi/agent/skills/base.py` | UPDATE | 添加公共 JSON 解析、统一消息格式 |
| `lingyi/agent/skills/inquiry.py` | UPDATE | 使用公共 JSON 解析 |
| `lingyi/agent/skills/safety_guard.py` | UPDATE | 使用公共 JSON 解析 |
| `lingyi/agent/skills/treatment.py` | UPDATE | 使用公共 JSON 解析 |
| `lingyi/agent/skills/rag_search.py` | UPDATE | 使用公共 JSON 解析 |
| `lingyi/agent/skills/writer.py` | UPDATE | 修复 fire-and-forget |
| `lingyi/agent/skills/diagnosis.py` | UPDATE | 统一消息格式 |
| `lingyi/agent/memory/summarizer.py` | UPDATE | 统一消息格式 |
| `lingyi/storage/checkpointer.py` | UPDATE | 使用 from_conn_string |
| `lingyi/storage/sqlite.py` | UPDATE | 连接复用 |
| `lingyi/api/routes/chat.py` | UPDATE | WebSocket 流式输出 |
| `lingyi/ui/chat.py` | UPDATE | 流式接收显示 |
| `.env` | UPDATE | 修复变量名 |
| `tests/` | UPDATE | 补充测试 |

## Tasks

### Phase 1: LLM 层优化（解决超时和重试）

#### Task 1.1: Settings 添加 LLM 超时/重试配置
- **File**: `lingyi/config.py`
- **Action**: 添加 `llm_timeout: int = Field(default=30)` 和 `llm_max_retries: int = Field(default=3)`
- **Validate**: test_config.py 验证新字段

#### Task 1.2: DashScopeLLM 传入 timeout 和 max_retries
- **File**: `lingyi/models/dashscope.py`
- **Action**: `ChatOpenAI(..., timeout=settings.llm_timeout, max_retries=settings.llm_max_retries)`
- **Mirror**: ChatOpenAI 文档确认参数名 `timeout`（非 request_timeout）和 `max_retries`
- **Validate**: 构造函数参数正确传递

#### Task 1.3: 统一 BaseLLM 接口为接收 LangChain 消息对象
- **File**: `lingyi/models/base.py`, `lingyi/models/dashscope.py`
- **Action**:
  - `BaseLLM.ainvoke` 签名改为 `ainvoke(messages: list[BaseMessage], ...) -> str`
  - 删除 `DashScopeLLM.ainvoke` 中的 dict→message 转换代码
  - 所有 skill 的 `build_messages()` 改为返回 `list[BaseMessage]`
- **Why**: 消除每次调用的格式转换开销，与 LangChain 生态一致
- **Validate**: 全部现有测试通过

### Phase 2: 流式输出（解决用户感知慢的问题）

#### Task 2.1: WebSocket 改用 astream 流式推送
- **File**: `lingyi/api/routes/chat.py`
- **Action**: WebSocket 端点改用 `graph.astream(state_input, stream_mode="messages", config=config)` 流式推送 token
- **Mirror**: LangGraph 文档 `stream_mode="messages"` 返回 `(message_chunk, metadata)` 元组
- **Validate**: WebSocket 客户端能收到增量 token

#### Task 2.2: Streamlit 前端支持流式显示
- **File**: `lingyi/ui/chat.py`
- **Action**: 使用 WebSocket 连接接收流式 token，`st.write_stream()` 显示
- **Validate**: UI 能逐步显示回复内容

### Phase 3: 存储层优化

#### Task 3.1: 修复 Checkpointer 创建方式
- **File**: `lingyi/storage/checkpointer.py`
- **Action**: 使用 `AsyncSqliteSaver.from_conn_string(db_path)` 替代手动 `aiosqlite.connect()`。添加 `setup()` 调用确保表已创建
- **Mirror**: LangGraph 文档确认 `from_conn_string` 是推荐用法
- **Validate**: 会话状态能正确持久化和恢复

#### Task 3.2: SQLite 连接复用
- **File**: `lingyi/storage/sqlite.py`
- **Action**: `_get_conn()` 改为 lazy-init 持久连接模式：首次调用时创建 `aiosqlite.connect()`，后续复用同一个连接。添加 `close()` 方法用于清理
- **Why**: 当前每次 DB 操作都新建+关闭连接，开销很大
- **Validate**: 并发请求不出现 "database is locked"，操作正常

### Phase 4: 代码规范化

#### Task 4.1: 抽取公共 JSON 解析工具
- **File**: `lingyi/agent/skills/base.py`
- **Action**: 添加 `parse_json_response(text: str, fallback: Any = None) -> dict` 静态方法。包含 3 步解析：直接 parse → fenced code block → regex extraction → fallback
- **Why**: inquiry.py, safety_guard.py, treatment.py, rag_search.py 有完全相同的 `_parse_response()` 代码（4 处重复）
- **Validate**: 现有 test_json_parsing.py 测试通过

#### Task 4.2: 各 Skill 统一使用公共 JSON 解析
- **Files**: `inquiry.py`, `safety_guard.py`, `treatment.py`, `rag_search.py`
- **Action**: 删除各自的 `_parse_response()` 方法，改为调用 `BaseSkill.parse_json_response()`
- **Validate**: 各 skill 的 JSON 解析行为不变

#### Task 4.3: WriterSkill 修复 fire-and-forget
- **File**: `lingyi/agent/skills/writer.py`
- **Action**: `asyncio.create_task()` 改为 `await asyncio.wait_for(self._extract_and_save(state, messages), timeout=15)`
- **Why**: 当前 create_task 可能导致画像更新在 event loop 关闭时丢失
- **Validate**: 画像更新完成后才返回，超时不会阻塞

#### Task 4.4: 消息构建统一为 LangChain 消息格式
- **Files**: `base.py`, `inquiry.py`, `diagnosis.py`, `treatment.py`, `safety_guard.py`, `summarizer.py`
- **Action**: `build_messages()` 返回 `list[BaseMessage]`（SystemMessage/HumanMessage/AIMessage），不再返回 `list[dict]`
- **Validate**: 所有 skill 正常工作

### Phase 5: Bug 修复和测试

#### Task 5.1: 修复 .env 变量名不匹配
- **File**: `.env`
- **Action**: `EMBEDDING_STRATEGY=local` 改为 `EMBEDDING_MODE=local`
- **Why**: Settings 字段名是 `embedding_mode`，pydantic-settings 不会读取 `EMBEDDING_STRATEGY`

#### Task 5.2: 补充超时和流式测试
- **File**: `tests/test_agent_flow.py` (新建)
- **Action**: 添加测试：
  - LLM 超时场景 → 图正确返回错误消息
  - 完整 inquiry→diagnosis→treatment 流程（stub LLM）
  - JSON 解析的各种边界情况
- **Validate**: `pytest tests/ -v` 全部通过

## Validation

```bash
conda activate lingyi

# 全部测试
pytest tests/ -v

# 启动后端
uvicorn lingyi.api.app:app --reload --port 8000

# 启动前端
streamlit run lingyi/ui/app.py

# 验证超时配置
python -c "from lingyi.config import get_settings; s = get_settings(); print(f'timeout={s.llm_timeout}, retries={s.llm_max_retries}')"

# 验证流式输出
python -c "
import asyncio
async def test():
    from lingyi.api.deps import get_agent, get_settings
    agent = get_agent(get_settings())
    async for chunk in agent.astream({'messages': []}, stream_mode='messages'):
        print(chunk)
asyncio.run(test())
"
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| 接口变更导致现有调用方不兼容 | Medium | 分阶段修改，每阶段运行测试 |
| 流式输出与 checkpointer 兼容性 | Low | checkpointer 在 stream 模式下仍正常工作 |
| SQLite 持久连接并发写入锁冲突 | Low | 使用 WAL 模式 |

## Acceptance

- [ ] LLM 调用有 30s 超时保护，不再无限阻塞
- [ ] WebSocket 支持流式 token 输出
- [ ] Streamlit 前端能逐步显示回复
- [ ] Checkpointer 使用 `from_conn_string` 标准方式
- [ ] SQLite 连接复用，不再每次新建
- [ ] 公共 JSON 解析消除 4 处重复代码
- [ ] Writer 任务不再 fire-and-forget
- [ ] .env 变量名修复
- [ ] 全部测试通过
- [ ] 所有 LangChain/LangGraph API 使用符合官方文档
