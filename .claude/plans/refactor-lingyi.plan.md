# Plan: LingYi 灵医 — 全项目重构

**Source**: `refactor-lingyi.md` + 当前代码库全面分析
**Complexity**: Large (12 个阶段，涉及全部模块重写)
**Estimated Duration**: 分阶段实施，每阶段独立可验证

---

## 一、现状问题总结

### 架构问题（从代码中确认）
| # | 问题 | 文件 | 影响 |
|---|---|---|---|
| 1 | 5 个全局单例（`config`, `model_manager`, `vector_client`, `safety_engine`, `profile_manager`）| 各模块顶部 | 无法注入、无法 mock，测试必须 monkey-patch |
| 2 | `config.py` 导入时执行 `os.environ["CUDA_VISIBLE_DEVICES"]="1"` 和 `load_dotenv(override=True)` | `config.py:1-6` | 副作用污染全局环境 |
| 3 | `app.py` 349 行混合认证/会话/文件上传/图调用 | `app.py` | 职责混乱，不可测试 |
| 4 | 每个 skill 自己 `open()` 读 `.md`，无基类 | `inquiry.py`, `diagnosis.py` 等 | 重复代码，无统一接口 |
| 5 | `rag_search.py` 混合检索/重排/评分/重写四个职责 | `agent/skills/rag_search.py:1-191` | 违反单一职责 |
| 6 | `agent/prompts.py` 内容与各 skill `.md` 重复且未被使用 | `agent/prompts.py` | 死代码 |
| 7 | `rag_search.md` 是占位符（"暂时置空"） | `agent/skills/rag_search.md` | RAG 评估/重写无 prompt 规范 |

### 数据问题（从 TCM_data/ 探索确认）
| # | 问题 | 影响 |
|---|---|---|
| 8 | 6 个古籍文本格式各异：条文体（伤寒论/金匮要略）、编号条目体（温病条辨）、药物条目体（神农本草经）、对话体（黄帝内经）、章节体（脉经） | 需要 6 种不同的 chunker |
| 9 | 部分文件含独立页码行（如 `217`）和来源标注（`中国哲学书电子化计划`） | 切分前需清洗 |
| 10 | `ingest.py` 硬编码了每个文本的处理逻辑，无抽象 | 无法扩展新书 |

### 工程问题
| # | 问题 | 影响 |
|---|---|---|
| 11 | 无 `requirements.txt` 或 `pyproject.toml` | 依赖全靠猜 |
| 12 | 测试是 5 个独立脚本，3 个依赖真实 API | 无法 CI |
| 13 | 无结构化日志，全用 `print()` | 生产环境无法排查 |
| 14 | 无自定义异常，出错 `except: pass` | 错误被静默吞掉 |
| 15 | 所有调用同步阻塞 | 并发性能差 |

---

## 二、目标架构

### 整体架构：FastAPI 后端 + Streamlit 前端

```
┌─────────────────────────────────────────────────────┐
│                   Streamlit UI (thin client)         │
│   lingyi/ui/auth.py · chat.py · sidebar.py          │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────────┐
│                   FastAPI Backend                    │
│   lingyi/api/routes/chat.py · health.py · threads.py│
│   lingyi/api/deps.py (依赖注入) · schemas.py        │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              Core Business Logic (纯 Python)         │
│   lingyi/agent/ · rag/ · safety/ · storage/         │
│   ← 不依赖 FastAPI 或 Streamlit，可独立测试          │
└─────────────────────────────────────────────────────┘
```

**为什么用 FastAPI**:
- Agent 逻辑与 UI 解耦 — Core 层不依赖任何 Web 框架
- 支持多种消费方 — Streamlit UI、curl、前端 SPA
- WebSocket 支持流式输出 — 比 `st.spinner` 更灵活
- 自动生成 OpenAPI 文档 — 方便调试
- 测试友好 — `TestClient` 可直接测 API

**技术栈版本要求**:
- LangChain ≥ 1.0, LangGraph ≥ 1.0
- FastAPI ≥ 0.115, Streamlit ≥ 1.40
- Python ≥ 3.12

### 设计原则
- **全链路异步** — API 路由 → Agent → LLM → Storage 全部 `async/await`
- **依赖注入** — 所有外部依赖通过构造函数注入，不用全局单例
- **接口抽象** — RAG、Embedding、Storage 都有抽象基类 + 多实现
- **Skill 规范** — 统一的 `BaseSkill` 基类，自动加载 `.md` prompt
- **数据管道化** — TCM 数据处理用 `Chunker` 策略模式
- **pytest 驱动** — 所有测试用 pytest，mock 所有外部依赖
- **Core 层零框架依赖** — `lingyi/agent/` 和 `lingyi/rag/` 不 import FastAPI 或 Streamlit
- **充分注释** — 每个类、方法、关键逻辑块必须有中文注释

### 目标目录结构

```
LingYi/
├── lingyi/                          # 主包
│   ├── __init__.py
│   ├── config.py                    # pydantic-settings，无副作用
│   ├── exceptions.py                # 统一异常层次
│   ├── logging.py                   # 日志配置
│   ├── models/                      # 模型抽象层
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseLLM, BaseEmbedding, BaseReranker
│   │   ├── dashscope.py             # DashScope/OpenAI 兼容实现
│   │   ├── local.py                 # 本地 HuggingFace 实现
│   │   └── factory.py               # create_llm(), create_embeddings()
│   ├── agent/                       # LangGraph 智能体
│   │   ├── __init__.py
│   │   ├── graph.py                 # 图定义 + create_agent() 工厂
│   │   ├── state.py                 # AgentState
│   │   ├── skills/
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # BaseSkill(ABC)
│   │   │   ├── inquiry.py + .md
│   │   │   ├── diagnosis.py + .md
│   │   │   ├── treatment.py + .md
│   │   │   ├── safety_guard.py + .md
│   │   │   ├── rag_search.py + .md  # 补充完整 prompt
│   │   │   ├── reader.py
│   │   │   └── writer.py
│   │   └── memory/
│   │       ├── __init__.py
│   │       ├── checkpointer.py
│   │       └── summarizer.py
│   ├── rag/                         # RAG 子系统
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseRAGClient(ABC)
│   │   ├── mock.py                  # MockRAGClient
│   │   ├── chroma.py                # ChromaRAGClient
│   │   └── reranker.py              # 重排逻辑
│   ├── safety/                      # 安全校验
│   │   ├── __init__.py
│   │   └── rules.py                 # SafetyEngine
│   ├── storage/                     # 持久化层
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseUserStore, BaseProfileStore
│   │   ├── sqlite.py                # SQLite 实现
│   │   └── checkpointer.py
│   ├── parsers/                     # 文件解析
│   │   ├── __init__.py
│   │   └── file_parser.py
│   ├── api/                         # FastAPI 后端
│   │   ├── __init__.py
│   │   ├── app.py                   # create_app() 工厂
│   │   ├── deps.py                  # 依赖注入
│   │   ├── schemas.py               # Pydantic 模型
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── chat.py
│   │       ├── threads.py
│   │       ├── profiles.py
│   │       └── health.py
│   └── ui/                          # Streamlit 前端
│       ├── __init__.py
│       ├── app.py                   # 主入口
│       ├── auth.py
│       ├── chat.py
│       └── sidebar.py
├── data_pipeline/                   # TCM 数据处理
│   ├── __init__.py
│   ├── base.py                      # BaseChunker(ABC), Chunk 数据类
│   ├── cleaners.py                  # 通用清洗函数
│   ├── chunkers/
│   │   ├── __init__.py
│   │   ├── shanghan.py              # 伤寒论 — 按条文切分
│   │   ├── wenbing.py               # 温病条辨 — 按编号条目切分
│   │   ├── shennong.py              # 神农本草经 — 按药物条目切分
│   │   ├── maijing.py               # 脉经 — 按章节切分
│   │   ├── jingui.py                # 金匮要略 — 去重 + 按条文切分
│   │   ├── suwen.py                 # 黄帝内经-素问 — 去重 + 按章节切分
│   │   └── registry.py              # ChunkerRegistry
│   ├── ingest.py                    # 入口脚本
│   └── mock_data.py                 # 生成 mock RAG 测试数据
├── tests/                           # pytest 测试套件
│   ├── conftest.py                  # 公共 fixtures
│   ├── test_config.py
│   ├── test_safety_rules.py
│   ├── test_inquiry.py
│   ├── test_diagnosis.py
│   ├── test_treatment.py
│   ├── test_rag_search.py
│   ├── test_summarizer.py
│   ├── test_json_parsing.py
│   ├── test_graph_flow.py
│   ├── test_api/
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
│   ├── architecture.md
│   ├── skills.md
│   ├── rag.md
│   ├── data_pipeline.md
│   └── deployment.md
├── TCM_data/                        # 原始数据（保持不动）
├── storage/                         # 运行时数据（gitignore）
├── .env
├── .gitignore
├── pyproject.toml
├── CLAUDE.md
├── README.md
└── LICENSE
```

---

## 三、重构阶段

### Phase 0: 准备工作（基础设施）

**目标**: 搭建新项目骨架，声明所有依赖，清理旧数据。

**Tasks**:
1. 删除旧的 `storage/chroma_db/`（用户已同意）
2. 创建 `pyproject.toml`，声明所有依赖：
   - 核心: `langchain>=1.0`, `langchain-core>=1.0`, `langchain-openai>=1.0`, `langgraph>=1.0`, `langgraph-checkpoint-sqlite>=1.0`
   - FastAPI: `fastapi>=0.115`, `uvicorn[standard]>=0.34`, `websockets>=14.0`
   - Streamlit: `streamlit>=1.40`, `extra-streamlit-components>=1.0`
   - 异步: `aiosqlite>=0.20`, `aiofiles>=24.0`, `httpx>=0.27`
   - 认证: `pyjwt>=2.10`, `bcrypt>=4.2`
   - 配置: `pydantic-settings>=2.0`
   - 向量库: `chromadb>=0.6`
   - Embedding: `sentence-transformers>=3.0`, `langchain-huggingface>=0.1`
   - 文件解析: `pypdf2>=3.0`, `python-docx>=1.0`
   - 工具: `python-dotenv>=1.0`, `tqdm>=4.0`
   - Dev: `pytest>=8.0`, `pytest-asyncio>=0.24`, `httpx>=0.27`, `ruff>=0.8`
3. 创建 `lingyi/` 包目录结构（所有 `__init__.py`）
4. 创建 `data_pipeline/` 包目录结构
5. 创建 `tests/` 目录结构
6. 创建 `docs/` 目录
7. 更新 `.gitignore`（新增 `storage/*.db`, `storage/chroma_db/`, `storage/chunks/`, `.ruff_cache/`）

**Validate**: `pip install -e ".[dev]"` 成功，`import lingyi` 不报错

---

### Phase 1: Config + 异常 + 日志（核心基础）

**目标**: 消除 config 的导入副作用，建立统一异常和日志体系。

**Tasks**:
1. **重写 `lingyi/config.py`** — 用 `pydantic-settings` 的 `BaseSettings`：
   - 不再在模块级调 `load_dotenv()` 或设 `os.environ`
   - 字段: `dashscope_api_key`, `base_url`, `model_name`, `embedding_mode` ("local"/"online"), `rag_mode` ("mock"/"chroma"), `log_level`, 所有 RAG 参数
   - 通过 `model_config = SettingsConfigDict(env_file=".env")` 自动加载
   - 提供 `get_settings()` 工厂函数（带 `lru_cache`）

2. **创建 `lingyi/exceptions.py`** — 统一异常层次：
   ```python
   class LingYiError(Exception): ...
   class SafetyViolationError(LingYiError): ...
   class RAGSearchError(LingYiError): ...
   class ModelCallError(LingYiError): ...
   class ConfigError(LingYiError): ...
   ```

3. **创建 `lingyi/logging.py`** — 日志配置：
   - 用 Python 标准 `logging` 模块
   - 格式: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`
   - 从 `Settings.log_level` 读取级别
   - 每个模块用 `logger = logging.getLogger(__name__)`

**Validate**: `pytest tests/test_config.py` — 验证 settings 加载、默认值、环境变量覆盖

---

### Phase 2: 模型抽象层

**目标**: 将 LLM/Embedding/Reranker 从 `model_provider.py` 拆分为抽象 + 多实现。

**Tasks**:
1. **创建 `lingyi/models/base.py`** — 抽象类：
   - `BaseLLM(ABC)`: `async def ainvoke(messages) -> str`
   - `BaseEmbedding(ABC)`: `async def aembed_documents(texts) -> List[List[float]]`
   - `BaseReranker(ABC)`: `async def arerank(query, docs) -> List[Doc]`

2. **创建 `lingyi/models/dashscope.py`** — DashScope 实现：
   - `DashScopeLLM`: 使用 `langchain-openai` 的 `ChatOpenAI`（DashScope 兼容 OpenAI 格式）
   - `DashScopeEmbedding`: 使用 DashScope embedding API
   - 从 `Settings` 注入 API key 和 base_url

3. **创建 `lingyi/models/local.py`** — 本地 HuggingFace 实现：
   - `LocalEmbedding`: `sentence-transformers` 的 BGE-M3
   - 支持 CUDA/CPU 自动回退

4. **创建 `lingyi/models/factory.py`** — 工厂函数：
   - `create_llm(settings) -> BaseLLM`
   - `create_embeddings(settings) -> BaseEmbedding`
   - `create_reranker(settings) -> BaseReranker`

**Validate**: `pytest tests/test_factory.py` — 验证工厂函数根据 config 返回正确类型

---

### Phase 3: Storage 抽象

**目标**: 将 `profile_manager.py` 拆分为用户/画像/线程管理，建立抽象接口。

**Tasks**:
1. **创建 `lingyi/storage/base.py`** — 抽象接口：
   - `BaseUserStore(ABC)`: `async create_user()`, `async verify_user()`
   - `BaseProfileStore(ABC)`: `async get_profile()`, `async update_profile()`
   - `BaseThreadStore(ABC)`: `async add_thread()`, `async get_threads()`, `async rename_thread()`, `async delete_thread()`

2. **重写 `lingyi/storage/sqlite.py`** — 实现三个接口：
   - 用 `aiosqlite` 替代 `sqlite3`
   - 密码哈希用 `bcrypt` 替代 SHA-256
   - 建表 SQL 抽到类常量中

3. **移动 `lingyi/storage/checkpointer.py`** — 保持 LangGraph checkpointer

**Validate**: `pytest tests/test_storage/test_sqlite_store.py` — 验证 CRUD 操作

---

### Phase 4: Safety 模块

**目标**: 将安全校验独立为纯 Python 模块，可通过构造函数注入。

**Tasks**:
1. **创建 `lingyi/safety/rules.py`** — 从 `tools/safety_rules.py` 迁移：
   - 保持 `EIGHTEEN_ANTAGONISMS` 和 `NINETEEN_INHIBITIONS` 数据
   - `SafetyEngine` 通过构造函数注入（不再模块级单例）
   - `check_prescription(herbs: List[str]) -> Tuple[bool, Optional[str]]`

**Validate**: `pytest tests/test_safety_rules.py` — 纯规则校验，无 API 依赖

---

### Phase 5: Skill 基类 + 重写各 Skill

**目标**: 统一 Skill 加载机制，每个 Skill 通过构造函数注入依赖。

**Tasks**:
1. **创建 `lingyi/agent/skills/base.py`** — `BaseSkill(ABC)`：
   - `_load_prompt()`: 用 `inspect` 模块找到子类文件所在目录，读取同名 `.md`
   - `build_messages(state) -> List[BaseMessage]`: 模板方法，子类可覆盖
   - `execute(state) -> dict`: 抽象方法
   - `node(state) -> dict`: LangGraph 节点入口，包装 `execute`

2. **逐个重写 Skill**（逻辑迁移，接入 BaseSkill）：
   - `inquiry.py` — 保持 JSON 解析逻辑，注入 LLM
   - `diagnosis.py` — 注入 LLM
   - `treatment.py` — 注入 LLM + SafetyEngine
   - `safety_guard.py` — 注入 LLM
   - `reader.py` — 注入 FileParser
   - `writer.py` — 注入 LLM + Storage

3. **补充 `rag_search.md`** — 当前是占位符，需写完整 prompt

**Validate**: `pytest tests/test_inquiry.py`, `test_diagnosis.py`, `test_treatment.py` — mock LLM

---

### Phase 6: RAG 子系统

**目标**: 建立 RAG 抽象接口，支持 mock/chroma 双模式。

**Tasks**:
1. **创建 `lingyi/rag/base.py`** — 抽象接口：
   ```python
   class BaseRAGClient(ABC):
       async def search(self, query: str, top_k: int = 3) -> List[Dict]: ...
       async def hybrid_search(self, query: str, n_results: int = 10) -> List[Dict]: ...
   ```

2. **创建 `lingyi/rag/mock.py`** — `MockRAGClient`：
   - 从 JSON 文件加载预设召回结果
   - 支持正则匹配 query pattern
   - 用于本地开发和测试

3. **创建 `lingyi/rag/chroma.py`** — `ChromaRAGClient`：
   - 从 `tools/vector_db_client.py` 重构
   - 通过构造函数注入 embedding model
   - 支持 `asyncio.to_thread()` 包装同步 ChromaDB 调用

4. **创建 `lingyi/rag/reranker.py`** — 重排逻辑：
   - `BaseReranker(ABC)`: `async def rerank(query, docs) -> List[Doc]`
   - `CrossEncoderReranker`: 真实重排
   - `MockReranker`: 返回原始顺序

5. **重写 `rag_search.py` skill** — 通过构造函数注入 RAG client

6. **创建 `data_pipeline/mock_data.py`** — 从 TCM 数据采样生成 mock RAG 测试数据

**Validate**: `pytest tests/test_rag_search.py` — 用 MockRAGClient

---

### Phase 7: Data Pipeline（TCM 数据处理）

**目标**: 为 6 本古籍建立独立的 chunker，统一数据管道。

**Tasks**:
1. **创建 `data_pipeline/base.py`**：
   - `Chunk` 数据类: `id`, `content`, `metadata`（book, chapter, clause 等）
   - `BaseChunker(ABC)`: `clean(text) -> str`, `chunk(text) -> List[Chunk]`

2. **创建 `data_pipeline/cleaners.py`** — 通用清洗：
   - `remove_page_numbers(text)`: 去除独立页码行（如 `217`）
   - `remove_source_markers(text)`: 去除 `中国哲学书电子化计划` 等
   - `deduplicate_chapters(text)`: 去除重复章节
   - `strip_separators(text)`: 去除 `----------`

3. **逐个实现 Chunker**（基于 TCM_data/ 文件结构分析）：

   | 书籍 | 文件特征 | 切分策略 |
   |---|---|---|
   | **伤寒论** | `### 辨太阳病...` 章节标题 + `1．` 数字条文 | 按条文切分，保留章节归属 |
   | **金匮要略** | 同伤寒论结构，有重复章节 | 先去重，再按条文切分 |
   | **温病条辨** | `一、二、...` 中文编号条目，含处方剂量 | 按编号条目切分，去页码 |
   | **神农本草经** | 按品类分组（玉石部/草部/...），每药一条 | 按药物条目切分，去页码 |
   | **脉经** | 数字章节 + `一曰` 子变体，14635 行 | 按章节切分，长章节按子变体子切分 |
   | **黄帝内经-素问** | 章节标题 + 对话体（黄帝/岐伯） | 先去重，按章节切分 |

4. **创建 `data_pipeline/chunkers/registry.py`** — `ChunkerRegistry`

5. **创建 `data_pipeline/ingest.py`** — 入口脚本：
   - 读取 TCM_data/ 下的清洗版文件
   - 用对应 chunker 切分
   - 输出 JSON chunks 到 `storage/chunks/`
   - 可选：写入 ChromaDB（仅 chroma 模式）

6. **创建 `data_pipeline/mock_data.py`** — 从切分结果采样生成 mock 数据

**Validate**: `pytest tests/test_data_pipeline/` — 每个 chunker 单元测试 + 清洗测试 + 注册表测试

---

### Phase 8: Graph 重写 + 依赖注入

**目标**: 重写 LangGraph 图，所有节点通过依赖注入获取。

**Tasks**:
1. **重写 `lingyi/agent/graph.py`**：
   - `create_agent(llm, rag_client, storage, safety_engine, settings) -> CompiledGraph`
   - 所有 node 通过 Skill 实例注入
   - 路由逻辑保持不变（master_router, rag_decision_logic, safety_check_logic 等）
   - 支持 mock/real RAG 模式切换

2. **重写 `lingyi/agent/memory/summarizer.py`** — 注入 LLM

3. **重写 `lingyi/agent/memory/checkpointer.py`** — 注入 db_path

**Validate**: `pytest tests/test_graph_flow.py` — 集成测试，mock 所有外部依赖

---

### Phase 9: FastAPI 后端

**目标**: 创建 REST API + WebSocket 接口，Agent 逻辑与 Web 框架解耦。

**Tasks**:
1. **创建 `lingyi/api/app.py`** — FastAPI 工厂：
   - `create_app(settings) -> FastAPI`
   - CORS、异常处理（统一返回 JSON）、lifespan 管理
   - 注册所有路由

2. **创建 `lingyi/api/deps.py`** — 依赖注入：
   - `get_settings()`, `get_agent()`, `get_storage()`, `get_rag_client()`
   - 用 FastAPI 的 `Depends` 机制

3. **创建 `lingyi/api/schemas.py`** — Pydantic 模型：
   - `ChatRequest`, `ChatResponse`
   - `ThreadCreate`, `ThreadResponse`
   - `ProfileResponse`

4. **创建路由**：
   - `routes/chat.py` — `POST /api/chat` + `WebSocket /api/ws/chat`
   - `routes/threads.py` — CRUD
   - `routes/profiles.py` — GET
   - `routes/health.py` — GET

**Validate**: `pytest tests/test_api/` — FastAPI TestClient

---

### Phase 10: Streamlit 前端重构

**目标**: 将 `app.py` 拆分为薄客户端，通过 HTTP 调 FastAPI。

**Tasks**:
1. **拆分 `app.py` → `lingyi/ui/`**：
   - `ui/auth.py` — 登录/注册表单（调 API）
   - `ui/chat.py` — 对话渲染 + 输入（调 API）
   - `ui/sidebar.py` — 侧边栏（调 API）
   - `ui/app.py` — 主入口

2. **Streamlit 不再直接 import agent/graph** — 全部通过 HTTP 调 FastAPI

**Validate**: `streamlit run lingyi/ui/app.py` 可正常运行

---

### Phase 11: 测试 + 文档

**目标**: 完善测试覆盖，编写项目文档。

**Tasks**:
1. **创建 `tests/conftest.py`** — 公共 fixtures：
   - `mock_llm` — 返回可控响应的 stub
   - `mock_rag_client` — MockRAGClient
   - `tmp_storage` — 临时 SQLite
   - `test_client` — FastAPI TestClient

2. **补全测试**（详见下方测试矩阵）

3. **编写文档**：
   - `docs/architecture.md` — 系统架构图 + 模块说明
   - `docs/skills.md` — 技能开发指南
   - `docs/rag.md` — RAG 子系统说明
   - `docs/data_pipeline.md` — 数据处理流程
   - `docs/deployment.md` — 部署指南

4. **重写 `README.md`** — 去掉夸大描述

**Validate**: `pytest tests/` 全部通过，`docs/` 下有完整文档

---

### Phase 12: 清理

**目标**: 删除旧代码，更新项目配置。

**Tasks**:
1. 删除旧的根目录文件（已被 `lingyi/` 包替代的）
2. 删除旧的 `test_*.py`（被 `tests/` 替代）
3. 删除过时的 md 文档（`灵医2.0.md`, `实施计划.md`, `灵医_技术报告.md`）
4. 更新 `CLAUDE.md`
5. 更新 `.pre-commit-config.yaml`（可选）

---

## 四、测试矩阵

| 测试文件 | 覆盖模块 | 依赖 | 类型 |
|---|---|---|---|
| `test_config.py` | `lingyi/config.py` | 无 | 单元 |
| `test_safety_rules.py` | `lingyi/safety/rules.py` | 无 | 单元 |
| `test_inquiry.py` | `lingyi/agent/skills/inquiry.py` | mock LLM | 单元 |
| `test_diagnosis.py` | `lingyi/agent/skills/diagnosis.py` | mock LLM | 单元 |
| `test_treatment.py` | `lingyi/agent/skills/treatment.py` | mock LLM + SafetyEngine | 单元 |
| `test_rag_search.py` | `lingyi/agent/skills/rag_search.py` | MockRAGClient | 单元 |
| `test_summarizer.py` | `lingyi/agent/memory/summarizer.py` | mock LLM | 单元 |
| `test_json_parsing.py` | JSON 提取逻辑 | 无 | 回归 |
| `test_graph_flow.py` | `lingyi/agent/graph.py` | mock 全部 | 集成 |
| `test_api/test_chat_route.py` | `lingyi/api/routes/chat.py` | FastAPI TestClient | API |
| `test_api/test_threads_route.py` | `lingyi/api/routes/threads.py` | FastAPI TestClient | API |
| `test_api/test_health_route.py` | `lingyi/api/routes/health.py` | FastAPI TestClient | API |
| `test_data_pipeline/test_shanghan_chunker.py` | 伤寒论 chunker | 无 | 单元 |
| `test_data_pipeline/test_wenbing_chunker.py` | 温病条辨 chunker | 无 | 单元 |
| `test_data_pipeline/test_cleaners.py` | 通用清洗 | 无 | 单元 |
| `test_data_pipeline/test_registry.py` | ChunkerRegistry | 无 | 单元 |
| `test_storage/test_sqlite_store.py` | SQLite 存储 | 临时 DB | 单元 |

**验收标准**:
- `pytest tests/` 全部通过（不需要真实 API）
- 每个测试文件至少 3 个测试用例

---

## 五、MCP 评估

**结论：不需要 MCP。**

理由：
- MCP 适合「让外部工具调用本系统」或「本系统调用外部标准化工具」
- LingYi 是自包含的 LangGraph Agent，所有工具都是内部模块
- 没有需要暴露给外部的 tool server
- 如果将来需要，可在 `lingyi/server/` 下新增

---

## 六、RAG 接口设计

支持两种 embedding 模式和两种 RAG 模式：

| 模式 | 说明 | 配置 |
|---|---|---|
| `mock` | 跳过 embedding 和向量检索，从文件加载预设结果 | `RAG_MODE=mock` |
| `chroma` | ChromaDB + BGE-M3 真实向量检索 | `RAG_MODE=chroma` |

Embedding 接口支持：
- **GPU 本地**: `EMBEDDING_MODE=local` — HuggingFace BGE-M3（sentence-transformers）
- **第三方 API**: `EMBEDDING_MODE=online` — DashScope embedding API

---

## 七、风险评估

| 风险 | 可能性 | 缓解措施 |
|---|---|---|
| LangGraph 1.0 API 变化导致 checkpointer 不兼容 | 中 | 锁定 `langgraph-checkpoint-sqlite` 版本，测试先行 |
| ChromaDB 异步包装性能问题 | 低 | 用 `asyncio.to_thread()` 包装，测试并发场景 |
| TCM 数据切分质量参差不齐 | 中 | 每个 chunker 独立测试，验证 chunk 数量和内容 |
| Streamlit → FastAPI 迁移后 Cookie/Session 兼容 | 中 | JWT token + localStorage，保留 Cookie 做 UI 层免登 |
| 全链路异步改造工作量大 | 中 | 分阶段实施，先同步后异步 |
| 旧代码删除后发现遗漏依赖 | 低 | 先迁移再删除，保留 git 历史 |

---

## 八、执行顺序

```
Phase 0  (准备)          ← 无依赖
    ↓
Phase 1  (Config+异常+日志) ← 无依赖
    ↓
Phase 2  (Models)        ← 依赖 Phase 1
    ↓
Phase 3  (Storage)       ← 依赖 Phase 1
    ↓
Phase 4  (Safety)        ← 依赖 Phase 1
    ↓
Phase 5  (Skills)        ← 依赖 Phase 1, 2, 3, 4
    ↓
Phase 6  (RAG)           ← 依赖 Phase 1, 2
    ↓
Phase 7  (Data Pipeline) ← 独立，可与 Phase 4-6 并行
    ↓
Phase 8  (Graph)         ← 依赖 Phase 5, 6
    ↓
Phase 9  (FastAPI)       ← 依赖 Phase 8
    ↓
Phase 10 (Streamlit)     ← 依赖 Phase 9
    ↓
Phase 11 (Tests+Docs)    ← 依赖所有
    ↓
Phase 12 (Cleanup)       ← 最后
```
