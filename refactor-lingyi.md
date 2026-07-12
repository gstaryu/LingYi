# Plan: LingYi 灵医 全项目重构

## 一、现状问题总结

### 架构问题
1. **全局单例泛滥** — `model_manager`, `config`, `vector_client`, `safety_engine`, `profile_manager` 全是模块级单例，无法注入、无法 mock，测试必须 monkey-patch
2. **职责混乱** — `model_provider.py` 同时管 LLM、Embedding、Reranker 三种模型；`rag_search.py` 混合了检索、重排、评分、重写四个职责；`app.py` 200+ 行混合了认证、会话、文件上传、图调用
3. **存储层错位** — `profile_manager.py` 放在 `storage/` 但它是业务逻辑（用户管理、画像管理），不是存储抽象
4. **Skill 加载无基类** — 每个 skill 自己 `open()` 读 `.md`，没有统一接口
5. **RAG 无抽象** — `vector_db_client.py` 直接耦合 ChromaDB + BGE-M3，无法切换 mock/real

### 数据问题
6. **TCM 数据结构不统一** — 6 个古籍文本格式各异（Q&A、条文、药物条目、对话体），需要不同的切分策略
7. **部分文件有重复内容** — 金匮要略、黄帝内经-素问 存在整章重复（两个版本合并）
8. **页面噪声** — 温病条辨、神农本草经、脉经 含大量独立页码行需剔除
9. **process_data.py 只处理了 4/6 个原始文件**，且硬编码了每个文本的处理逻辑

### 测试问题
10. **无测试框架** — 5 个独立脚本，3 个依赖真实 API，无法 CI
11. **覆盖率极低** — 无 config、tools、data pipeline 的测试

### 工程问题
12. **无 requirements.txt** — 依赖关系全靠猜
13. **config.py 导入时有副作用** — `os.environ["CUDA_VISIBLE_DEVICES"] = "1"` 在 import 时执行
14. **文档过度营销** — 技术报告和 README 中有大量夸大描述

---

## 二、目标架构

### 整体架构：FastAPI 后端 + Streamlit 前端

```
┌─────────────────────────────────────────────────────┐
│                   Streamlit UI (thin client)         │
│   ui/auth.py · ui/chat.py · ui/sidebar.py           │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────────┐
│                   FastAPI Backend                    │
│   api/routes/chat.py · api/routes/health.py         │
│   api/deps.py (依赖注入) · api/schemas.py           │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Core Business Logic (纯 Python)         │
│   agent/ · rag/ · safety/ · storage/ · models/      │
│   ← 不依赖 FastAPI 或 Streamlit，可独立测试          │
└─────────────────────────────────────────────────────┘
```

**为什么用 FastAPI**:
- 将 Agent 逻辑与 UI 解耦 — Core 层不依赖任何 Web 框架
- 支持多种消费方 — Streamlit UI、curl、前端 SPA、MCP（未来）
- WebSocket 支持流式输出 — 比 Streamlit 的 `st.spinner` 更灵活
- 自动生成 OpenAPI 文档 — 方便调试和第三方集成
- 测试友好 — `TestClient` 可以直接测 API，不需要启动服务器

**为什么保留 Streamlit**:
- 快速原型 — 登录/对话/文件上传/画像展示已实现
- 低前端成本 — 不需要写 React/Vue
- 渐进迁移 — 先用 Streamlit，将来可换任何前端

**技术栈版本要求**:
- **LangChain ≥ 1.0** (`langchain`, `langchain-core`, `langchain-openai`)
- **LangGraph ≥ 1.0** (`langgraph`, `langgraph-checkpoint-sqlite`)
- **FastAPI ≥ 0.115**
- **Streamlit ≥ 1.40**
- **Python ≥ 3.12**

**LangGraph 1.0 关键变化**（相比当前代码）:
- `add_messages` 仍可用但推荐用 `MessagesState` 或自定义 reducer
- `StateGraph` API 基本不变，但 checkpointer 来自 `langgraph-checkpoint-sqlite`
- `START`/`END` 仍从 `langgraph.graph` 导入
- `app.stream()` / `app.invoke()` API 不变

### 全链路异步设计

每一层都必须是 async：

| 层 | 当前 | 重构后 |
|---|---|---|
| API 路由 | 不存在 | `async def chat(request)` |
| Agent 调用 | `app.invoke()` / `app.stream()` | `await app.ainvoke()` / `async for event in app.astream()` |
| LLM 调用 | `llm.invoke()` | `await llm.ainvoke()` |
| Storage (SQLite) | `sqlite3`（同步阻塞） | `aiosqlite`（异步） |
| ChromaDB | 同步 | `asyncio.to_thread()` 包装（ChromaDB 原生不支持 async） |
| 文件解析 | 同步 `open()` | `aiofiles` + `asyncio.to_thread()` 给 CPU 密集部分 |
| RAG 检索 | 同步 | `await rag_client.ahybrid_search()` |
| Streamlit 调用 | 直接 import agent | `httpx.AsyncClient` 调 FastAPI |

**pyproject.toml 新增依赖**:
```toml
"aiosqlite>=0.20",
"aiofiles>=24.0",
"httpx>=0.27",          # Streamlit → FastAPI 异步客户端
```

### 你可能遗漏的 7 件事

**1. 结构化日志**
当前全部用 `print()`。重构后：
- 用 Python 标准 `logging` 模块（不用 loguru/structlog，避免额外依赖）
- 在 `config.py` 中统一配置日志级别和格式
- 每个模块 `logger = logging.getLogger(__name__)`
- API 层用 FastAPI 的 `logging` 中间件
- 日志格式：`%(asctime)s | %(levelname)s | %(name)s | %(message)s`

**2. 统一异常处理**
当前无自定义异常，出错直接 `print` 或 `except: pass`。重构后：
```python
# lingyi/exceptions.py
class LingYiError(Exception): ...
class SafetyViolationError(LingYiError): ...
class RAGSearchError(LingYiError): ...
class ModelCallError(LingYiError): ...
class ConfigError(LingYiError): ...
```
- FastAPI 层用 `@app.exception_handler(LingYiError)` 统一返回 JSON 错误
- Agent 层抛 `LingYiError`，由调用方决定如何处理

**3. 认证方案升级**
当前用 Cookie + SHA-256 密码，无 token 机制。重构后：
- FastAPI 用 JWT token（`python-jose` 或 `pyjwt`）
- 登录返回 `access_token`，前端存 `localStorage`
- API 路由用 `Depends(get_current_user)` 保护
- Streamlit 仍用 Cookie 做 UI 层免登，但 API 调用带 Bearer token
- 密码哈希用 `bcrypt` 替代 SHA-256（更安全）

**4. 流式输出**
当前 `app.invoke()` 是非流式的。重构后：
- FastAPI 提供 `WebSocket /api/ws/chat` 流式推送
- Agent 用 `app.astream()` 逐节点产出
- 每个节点执行完推一条 `{node: "inquiry", output: {...}}` 到 WebSocket
- Streamlit 端用 `websocket-client` 或 `st.experimental_streaming` 接收
- 或者用 SSE（Server-Sent Events）替代 WebSocket（更简单）

**5. 配置分环境管理**
当前 `.env` 一个文件，无环境区分。重构后：
```python
# config.py
class Settings(BaseSettings):  # 用 pydantic-settings
    model_config = SettingsDict(env_file=".env")

    # 通过 ENVIRONMENT 环境变量区分
    environment: str = "development"  # development / testing / production

    rag_mode: str = "mock"            # mock / chroma
    log_level: str = "INFO"           # DEBUG / INFO / WARNING
    ...
```
- `.env.development` — mock RAG, DEBUG 日志
- `.env.production` — chroma RAG, WARNING 日志
- `pydantic-settings` 替代手写 dataclass + `os.getenv`

**6. pre-commit + 代码质量**
- `.pre-commit-config.yaml` — black, ruff, mypy
- `pyproject.toml` 中配置 ruff 和 mypy
- CI 中跑 `pre-commit run --all-files`

**7. 数据库迁移策略**
当前 SQLite 表结构是 `_init_db()` 里硬编码的 `CREATE TABLE IF NOT EXISTS`。重构后：
- 用 Alembic 管理 SQLite schema 迁移
- 或者至少把建表 SQL 抽到 `storage/schema.sql` 文件中
- 版本号记录在 DB 里，启动时检查是否需要迁移

### 设计原则
- **全链路异步** — 从 API 路由到 Agent 调用到存储层，全部 `async/await`
- **依赖注入** — 所有外部依赖通过构造函数注入，不用全局单例
- **接口抽象** — RAG、Embedding、Storage 都有抽象基类 + 多实现
- **Skill 规范** — 统一的 `BaseSkill` 基类，自动加载 `.md` prompt
- **数据管道化** — TCM 数据处理用 `Chunker` 策略模式，每本书一个 chunker
- **pytest 驱动** — 所有测试用 pytest，mock 所有外部依赖
- **Core 层零框架依赖** — agent/rag/safety/storage 不 import FastAPI 或 Streamlit
- **充分注释** — 每个类、方法、关键逻辑块必须有中文注释，说明"做什么"和"为什么"

### 目标目录结构

```
LingYi/
├── lingyi/                          # 主包（从根目录平移）
│   ├── __init__.py
│   ├── config.py                    # 纯数据类，无副作用
│   ├── models/                      # 模型抽象层
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseLLM, BaseEmbedding, BaseReranker 抽象
│   │   ├── dashscope.py             # DashScope/OpenAI 兼容实现
│   │   ├── local.py                 # 本地 HuggingFace 实现
│   │   └── factory.py               # 工厂函数 create_llm(), create_embeddings()
│   ├── agent/                       # LangGraph 智能体
│   │   ├── __init__.py
│   │   ├── graph.py                 # 图定义 + 路由
│   │   ├── state.py                 # AgentState
│   │   ├── skills/                  # 技能节点
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # BaseSkill(ABC) — 自动加载 .md prompt
│   │   │   ├── inquiry.py + .md
│   │   │   ├── diagnosis.py + .md
│   │   │   ├── treatment.py + .md
│   │   │   ├── safety_guard.py + .md
│   │   │   ├── rag_search.py + .md
│   │   │   ├── reader.py
│   │   │   └── writer.py
│   │   └── memory/
│   │       ├── __init__.py
│   │       ├── checkpointer.py
│   │       └── summarizer.py
│   ├── rag/                         # RAG 子系统（独立模块）
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseRAGClient(ABC)
│   │   ├── mock.py                  # MockRAGClient — 手动/文件加载
│   │   ├── chroma.py                # ChromaRAGClient — 真实向量检索
│   │   └── reranker.py              # 重排逻辑（可选 mock/real）
│   ├── safety/                      # 安全校验
│   │   ├── __init__.py
│   │   └── rules.py                 # SafetyEngine
│   ├── storage/                     # 持久化层
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseUserStore, BaseProfileStore(ABC)
│   │   ├── sqlite.py                # SQLite 实现（用户、画像、线程）
│   │   └── checkpointer.py         # LangGraph checkpointer
│   ├── parsers/                     # 文件解析
│   │   ├── __init__.py
│   │   └── file_parser.py
│   ├── api/                         # FastAPI 后端
│   │   ├── __init__.py
│   │   ├── app.py                   # FastAPI application 工厂
│   │   ├── deps.py                  # 依赖注入（创建 agent、storage 等实例）
│   │   ├── schemas.py               # Pydantic 请求/响应模型
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── chat.py              # POST /chat, WebSocket /ws/chat
│   │       ├── threads.py           # CRUD /threads
│   │       ├── profiles.py          # GET /profiles/{id}
│   │       └── health.py            # GET /health
│   └── ui/                          # Streamlit 前端（薄客户端）
│       ├── __init__.py
│       ├── app.py                   # 主入口
│       ├── auth.py                  # 登录/注册
│       ├── chat.py                  # 对话区
│       └── sidebar.py               # 侧边栏
├── data_pipeline/                   # TCM 数据处理（独立于运行时）
│   ├── __init__.py
│   ├── base.py                      # BaseChunker(ABC)
│   ├── cleaners.py                  # 通用清洗（去页码、去重复）
│   ├── chunkers/                    # 每本书一个 chunker
│   │   ├── __init__.py
│   │   ├── shanghan.py              # 伤寒论 — 按条文切分
│   │   ├── wenbing.py               # 温病条辨 — 按编号条目切分
│   │   ├── shennong.py              # 神农本草经 — 按药物条目切分
│   │   ├── maijing.py               # 脉经 — 按章节切分
│   │   ├── jingui.py                # 金匮要略 — 去重 + 按条文切分
│   │   ├── suwen.py                 # 黄帝内经-素问 — 去重 + 按章节切分
│   │   └── registry.py              # ChunkerRegistry
│   ├── ingest.py                    # 入口脚本：解析 → 切分 → 写入
│   └── mock_data.py                 # 生成 mock RAG 测试数据
├── tests/                           # pytest 测试套件
│   ├── conftest.py                  # 公共 fixtures（mock LLM, mock RAG, tmp DB）
│   ├── test_config.py
│   ├── test_safety_rules.py
│   ├── test_inquiry.py
│   ├── test_diagnosis.py
│   ├── test_treatment.py
│   ├── test_rag_search.py
│   ├── test_summarizer.py
│   ├── test_json_parsing.py
│   ├── test_graph_flow.py
│   ├── test_api/                    # API 层测试
│   │   ├── test_chat_route.py
│   │   ├── test_threads_route.py
│   │   └── test_health_route.py
│   ├── test_data_pipeline/
│   │   ├── test_shanghan_chunker.py
│   │   ├── test_wenbing_chunker.py
│   │   ├── test_cleaners.py
│   │   └── test_registry.py
│   └── test_storage/
│       └── test_sqlite_store.py
├── docs/                            # 项目文档
│   ├── architecture.md              # 架构说明
│   ├── skills.md                    # 技能开发指南
│   ├── rag.md                       # RAG 子系统说明
│   ├── data_pipeline.md             # 数据管道说明
│   └── deployment.md                # 部署指南
├── TCM_data/                        # 原始数据（保持不动）
│   ├── data_row/                    # 原始文件
│   └── *_完整清洗版.txt              # 清洗后文件
├── storage/                         # 运行时数据（gitignore）
├── .env
├── .gitignore
├── pyproject.toml                   # 项目元数据 + 依赖
├── CLAUDE.md
├── README.md                        # 精简重写
└── LICENSE
```

---

## 三、重构阶段

### Phase 0: 准备工作（基础设施）
1. 删除旧的 `storage/chroma_db/`（用户已同意）
2. 创建 `pyproject.toml`，声明所有依赖（见下方依赖清单）
3. 更新 `.gitignore`（忽略 storage/, __pycache__, .env, *.db）
4. 创建 `lingyi/` 包结构，将现有代码平移进去
5. 更新所有 import 路径

**pyproject.toml 依赖清单**:
```toml
[project]
name = "lingyi"
version = "2.0.0"
requires-python = ">=3.12"

dependencies = [
    # LangChain / LangGraph 1.0+
    "langchain>=1.0",
    "langchain-core>=1.0",
    "langchain-openai>=1.0",
    "langgraph>=1.0",
    "langgraph-checkpoint-sqlite>=1.0",

    # FastAPI 后端
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "websockets>=14.0",

    # Streamlit 前端
    "streamlit>=1.40",
    "extra-streamlit-components>=1.0",

    # 异步支持
    "aiosqlite>=0.20",
    "aiofiles>=24.0",
    "httpx>=0.27",          # Streamlit → FastAPI 异步客户端

    # 认证
    "pyjwt>=2.10",
    "bcrypt>=4.2",

    # 配置管理
    "pydantic-settings>=2.0",

    # 数据库
    "chromadb>=0.6",

    # Embedding / Reranker（仅 chroma 模式）
    "sentence-transformers>=3.0; python_version<'4'",
    "langchain-huggingface>=0.1",

    # 文件解析
    "pypdf2>=3.0",
    "python-docx>=1.0",

    # 工具
    "python-dotenv>=1.0",
    "opencc-python-reimplemented>=0.1",  # 繁简转换
    "tqdm>=4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",          # FastAPI TestClient
    "ruff>=0.8",
    "mypy>=1.13",
    "pre-commit>=4.0",
]
```

### Phase 1: Config + Models（核心抽象）
1. **重写 `config.py`** — 纯 dataclass，无副作用，不调 `load_dotenv`
2. **创建 `models/base.py`** — `BaseLLM`, `BaseEmbedding`, `BaseReranker` 抽象类
3. **创建 `models/dashscope.py`** — DashScope/OpenAI 兼容实现
4. **创建 `models/local.py`** — 本地 HuggingFace 实现
5. **创建 `models/factory.py`** — 工厂函数，根据 config 返回实例
6. **测试**: `test_config.py`, `test_factory.py`

### Phase 2: Storage 抽象
1. **创建 `storage/base.py`** — `BaseUserStore`, `BaseProfileStore` 抽象
2. **重写 `storage/sqlite.py`** — 将 `profile_manager.py` 拆为：用户管理 + 画像管理 + 线程管理
3. **移动 `checkpointer.py`** — 保持 LangGraph checkpointer
4. **测试**: `test_storage/test_sqlite_store.py`

### Phase 3: Safety 模块
1. **移动 `safety_rules.py` → `safety/rules.py`**
2. 保持逻辑不变，改为通过构造函数注入 config
3. **测试**: `test_safety_rules.py`（纯单元测试，无 API 依赖）

### Phase 4: Skill 基类 + 重写各 Skill
1. **创建 `skills/base.py`** — `BaseSkill`:
   - 自动读取同目录同名 `.md` 作为 system prompt
   - 提供 `build_messages(state)` 模板方法
   - 子类只需实现 `execute(state) -> dict`
2. **逐个重写 Skill**:
   - `inquiry.py` — 保持逻辑，接入 BaseSkill
   - `diagnosis.py` — 同上
   - `treatment.py` — 同上，安全校验通过构造函数注入
   - `safety_guard.py` — 同上
   - `reader.py` — 同上
   - `writer.py` — 同上
3. **测试**: 每个 skill 一个测试文件，mock LLM

### Phase 5: RAG 子系统
1. **创建 `rag/base.py`** — `BaseRAGClient(ABC)`:
   ```python
   class BaseRAGClient(ABC):
       def search(self, query: str, top_k: int = 3) -> List[str]: ...
       def hybrid_search(self, query: str, n_results: int = 10) -> List[Dict]: ...
   ```
2. **创建 `rag/mock.py`** — `MockRAGClient`:
   - 支持从 JSON 文件加载预设召回结果
   - 支持手动传入文档列表
   - 用于本地开发和测试
3. **创建 `rag/chroma.py`** — `ChromaRAGClient`:
   - 从现有 `vector_db_client.py` 重构
   - 通过构造函数注入 embedding model
4. **创建 `rag/reranker.py`** — 重排逻辑抽象 + mock/real 实现
5. **重写 `rag_search.py` skill** — 通过构造函数注入 RAG client
6. **Config 新增**: `RAG_MODE = "mock" | "chroma"`
7. **测试**: `test_rag_search.py`（用 MockRAGClient）

### Phase 6: Data Pipeline
1. **创建 `data_pipeline/base.py`** — `BaseChunker(ABC)`:
   ```python
   class BaseChunker(ABC):
       def clean(self, text: str) -> str: ...       # 通用清洗
       def chunk(self, text: str) -> List[Chunk]: ... # 书特定切分
   ```
   `Chunk` = `{"id": str, "content": str, "metadata": dict}`
2. **创建 `data_pipeline/cleaners.py`** — 通用清洗函数:
   - `remove_page_numbers(text)` — 去除独立页码行
   - `deduplicate_chapters(text)` — 去除重复章节
   - `strip_separators(text)` — 去除 `----------`
3. **逐个实现 Chunker**:
   - `shanghan.py` — 按条文（数字编号）切分，保留方剂引用
   - `wenbing.py` — 按编号条目（一、二、三）切分，去页码
   - `shennong.py` — 按药物条目切分，去页码，按品类分组
   - `maijing.py` — 按章节切分，长章节内按 Q&A 或 `一曰` 子切分，去页码
   - `jingui.py` — 先去重，再按条文切分，方剂块跟随前文
   - `suwen.py` — 先去重，再按章节切分，长章节按对话轮次子切分
4. **创建 `data_pipeline/registry.py`** — `ChunkerRegistry`，根据书名返回对应 chunker
5. **创建 `data_pipeline/ingest.py`** — 入口脚本：
   - 读取 TCM_data/ 下的清洗版文件
   - 用对应 chunker 切分
   - 输出 JSON chunks 到 `storage/chunks/`
   - 可选：写入 ChromaDB（仅 chroma 模式）
6. **创建 `data_pipeline/mock_data.py`** — 从切分结果中采样生成 mock RAG 测试数据
7. **测试**: 每个 chunker 一个测试文件 + `test_cleaners.py` + `test_registry.py`

### Phase 7: Graph 重写
1. **重写 `agent/graph.py`**:
   - 所有 node 通过依赖注入获取（不再 import 全局单例）
   - 路由逻辑保持不变
   - 支持 mock 和 real RAG 模式的切换
2. **创建工厂函数** `create_agent(rag_mode, storage, ...)` — 组装完整图

### Phase 8: FastAPI 后端
1. **创建 `api/app.py`** — FastAPI application 工厂:
   - `create_app(config, agent, storage) -> FastAPI`
   - CORS、异常处理、lifespan 管理
2. **创建 `api/deps.py`** — 依赖注入:
   - `get_agent()` — 创建/获取 LangGraph agent 实例
   - `get_storage()` — 获取存储实例
   - `get_rag_client()` — 根据 config 返回 mock/chroma RAG client
3. **创建 `api/schemas.py`** — Pydantic 模型:
   - `ChatRequest(messages, thread_id, files)`
   - `ChatResponse(response, thread_id)`
   - `ThreadCreate/ThreadResponse`
   - `ProfileResponse`
4. **创建 API 路由**:
   - `routes/chat.py` — `POST /api/chat`（同步）+ `WebSocket /api/ws/chat`（流式）
   - `routes/threads.py` — `GET/POST/DELETE /api/threads`
   - `routes/profiles.py` — `GET /api/profiles/{thread_id}`
   - `routes/health.py` — `GET /api/health`
5. **测试**: `test_api/` — 用 FastAPI `TestClient`，mock agent

### Phase 9: Streamlit 前端重构
1. **拆分 `app.py` → `ui/`**:
   - `ui/auth.py` — 登录/注册表单（改为调 API）
   - `ui/chat.py` — 对话渲染 + 输入（改为调 API）
   - `ui/sidebar.py` — 侧边栏（改为调 API）
   - `ui/app.py` — 主入口，组装各模块
2. **Streamlit 不再直接 import agent/graph** — 全部通过 HTTP 调 FastAPI
3. 启动方式: `uvicorn lingyi.api.app:app` + `streamlit run lingyi/ui/app.py`

### Phase 10: 测试 + 文档
1. **创建 `tests/conftest.py`** — 公共 fixtures:
   - `mock_llm` — 返回可控响应的 stub
   - `mock_rag_client` — 返回预设文档的 MockRAGClient
   - `tmp_storage` — 临时 SQLite 数据库
   - `test_client` — FastAPI TestClient
2. **补全测试**:
   - `test_config.py`
   - `test_safety_rules.py` — 纯规则校验，无 API
   - `test_inquiry.py` — mock LLM，验证意图分类
   - `test_diagnosis.py` — mock LLM，验证辨证流程
   - `test_treatment.py` — mock LLM + safety engine
   - `test_rag_search.py` — mock RAG client
   - `test_summarizer.py` — 从现有迁移
   - `test_json_parsing.py` — 从现有迁移
   - `test_graph_flow.py` — 集成测试，mock 所有外部
   - `test_api/test_chat_route.py` — FastAPI TestClient
   - `test_api/test_threads_route.py`
   - `test_api/test_health_route.py`
   - `test_data_pipeline/` — 各 chunker 单元测试
   - `test_storage/test_sqlite_store.py`
3. **写文档**:
   - `docs/architecture.md` — 系统架构图 + 模块说明
   - `docs/skills.md` — 如何开发新 skill
   - `docs/rag.md` — RAG 子系统：mock 模式 vs chroma 模式
   - `docs/data_pipeline.md` — 数据处理流程 + 各书切分策略
   - `docs/deployment.md` — 部署指南（FastAPI + Streamlit 启动方式）
4. **重写 `README.md`** — 去掉夸大描述，保留实用信息

### Phase 11: 清理
1. 删除旧的根目录文件（已被 `lingyi/` 包替代的）
2. 删除 `TCM_data/process_data.py` 和 `TCM_data/test.py`（被 `data_pipeline/` 替代）
3. 删除旧的 `test_*.py`（被 `tests/` 替代）
4. 删除 `灵医2.0.md`, `实施计划.md`, `灵医_技术报告.md`（内容已整合进 docs/）
5. 更新 `CLAUDE.md`

---

## 四、MCP 评估

**结论：不需要 MCP。**

理由：
- MCP 适合「让外部工具调用本系统」或「本系统调用外部标准化工具」
- LingYi 是一个自包含的 LangGraph Agent，所有工具（RAG、Safety、Parser）都是内部模块
- 没有需要暴露给外部的 tool server，也没有需要调用的外部 MCP server
- 如果将来需要将灵医作为 MCP tool server 暴露，可以在 `lingyi/server/` 下新增，不影响当前重构

---

## 五、关键设计细节

### 5.1 依赖注入容器

不用 DI 框架，用简单的工厂 + 参数传递：

```python
# lingyi/agent/graph.py
def create_agent(
    llm: BaseLLM,
    rag_client: BaseRAGClient,
    storage: BaseProfileStore,
    safety_engine: SafetyEngine,
) -> CompiledGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("inquiry", InquirySkill(llm).node)
    workflow.add_node("rag_search", RAGSearchSkill(rag_client, llm).node)
    # ...
    return workflow.compile(checkpointer=...)
```

### 5.2 RAG Mock 数据格式

`storage/mock_rag_data.json`:
```json
{
  "queries": [
    {
      "query_pattern": "脾胃虚寒|腹胀|怕冷",
      "results": [
        {"content": "太阴之为病，腹满而吐...", "source": "伤寒论", "score": 0.92},
        {"content": "...", "source": "金匮要略", "score": 0.85}
      ]
    }
  ],
  "default_results": [
    {"content": "默认召回内容...", "source": "黄帝内经", "score": 0.6}
  ]
}
```

### 5.3 TCM Chunker 示例 — 伤寒论

```python
class ShanghanChunker(BaseChunker):
    """按条文（数字编号）切分，每条条文是一个独立语义单元。"""

    CLAUSE_PATTERN = re.compile(r'^(\d+)[．.]\s*(.*)', re.MULTILINE)

    def chunk(self, text: str) -> List[Chunk]:
        chunks = []
        current_chapter = ""
        for line in text.splitlines():
            if line.startswith("### "):
                current_chapter = line[4:].strip()
                continue
            match = self.CLAUSE_PATTERN.match(line)
            if match:
                clause_id = match.group(1)
                content = match.group(2)
                chunks.append(Chunk(
                    id=f"SHL_{clause_id}",
                    content=content,
                    metadata={"book": "伤寒论", "chapter": current_chapter, "clause": clause_id}
                ))
        return chunks
```

### 5.4 Skill 基类

```python
class BaseSkill(ABC):
    def __init__(self, llm: BaseLLM):
        self.llm = llm
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        md_path = Path(__file__).parent / f"{self.__class__.__name__.lower().replace('skill', '')}.md"
        # 实际用 inspect 模块找到子类文件所在目录
        return md_path.read_text(encoding="utf-8")

    @abstractmethod
    def execute(self, state: AgentState) -> dict: ...

    def node(self, state: AgentState) -> dict:
        """LangGraph node 入口，包装 execute。"""
        return self.execute(state)
```

---

## 六、执行顺序与依赖关系

```
Phase 0  (准备)
    ↓
Phase 1  (Config + Models) ← 无依赖
    ↓
Phase 2  (Storage) ← 依赖 Phase 1
    ↓
Phase 3  (Safety) ← 依赖 Phase 1
    ↓
Phase 4  (Skills) ← 依赖 Phase 1, 2, 3
    ↓
Phase 5  (RAG) ← 依赖 Phase 1, 4
    ↓
Phase 6  (Data Pipeline) ← 独立，可与 Phase 4-5 并行
    ↓
Phase 7  (Graph) ← 依赖 Phase 4, 5
    ↓
Phase 8  (FastAPI 后端) ← 依赖 Phase 7
    ↓
Phase 9  (Streamlit 前端) ← 依赖 Phase 8
    ↓
Phase 10 (Tests + Docs) ← 依赖所有
    ↓
Phase 11 (Cleanup) ← 最后
```

---

## 七、验收标准

- [ ] `pytest tests/` 全部通过（不需要真实 API）
- [ ] `uvicorn lingyi.api.app:app` 可启动，`/api/health` 返回 200
- [ ] `POST /api/chat` 可正常对话（mock RAG 模式）
- [ ] `RAG_MODE=mock` 时 `streamlit run lingyi/ui/app.py` 可完整运行
- [ ] `RAG_MODE=chroma` 时运行 `python data_pipeline/ingest.py` 后可正常检索
- [ ] 每个 TCM 古籍文本都被正确切分（验证 chunk 数量和内容）
- [ ] 安全校验（十八反十九畏）在 mock LLM 下可独立测试
- [ ] 无全局单例，所有依赖可注入可 mock
- [ ] `lingyi/agent/` 和 `lingyi/rag/` 不 import FastAPI 或 Streamlit
- [ ] `docs/` 下有完整文档
- [ ] `README.md` 准确、简洁、无夸大
