# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LingYi (灵医)** is a Traditional Chinese Medicine (TCM) diagnostic multi-agent system. It uses LangGraph for agent workflow orchestration, Qwen3 (via Alibaba Cloud DashScope) as the LLM, FastAPI for the backend API, Streamlit for the web UI, and ChromaDB for RAG retrieval over classical TCM texts.

## Constraints

- **只允许操作 `D:\PycharmProjects\LingYi` 文件夹**，项目目录以外的文件只可读、不可写。
- 可以在当前项目目录内安装任意 Python 包。

## Environment

| 项目 | 值 |
|---|---|
| Conda 环境名 | `lingyi` |
| Python 版本 | `3.12` |

激活环境：`conda activate lingyi`

## Architecture

```
LingYi/
├── lingyi/                  # 主包
│   ├── config.py            # pydantic-settings 配置
│   ├── exceptions.py        # 统一异常层次
│   ├── logging.py           # 日志配置
│   ├── models/              # LLM/Embedding/Reranker 抽象
│   ├── agent/               # LangGraph 图 + 技能节点
│   │   ├── skills/          # inquiry, diagnosis, treatment, safety_guard, rag_search
│   │   └── memory/          # checkpointer, summarizer
│   ├── rag/                 # RAG 子系统（mock/chroma）
│   ├── safety/              # 十八反十九畏安全引擎
│   ├── storage/             # SQLite 持久化
│   ├── parsers/             # 文件解析
│   ├── api/                 # FastAPI 后端
│   └── ui/                  # Streamlit 前端
├── data_pipeline/           # TCM 数据处理（独立于运行时）
├── tests/                   # pytest 测试套件
├── docs/                    # 项目文档
└── TCM_data/                # 原始数据
```

## RAG 模式

- **`mock`** — 本地开发用。从文件加载预设结果。
- **`chroma`** — 生产用。ChromaDB + BGE-M3 向量检索。

Embedding 模式通过 `EMBEDDING_MODE` 切换：
- **`local`** — 本地 HuggingFace BGE-M3（GPU/CPU）
- **`online`** — DashScope Embedding API

## Commands

```bash
# FastAPI 后端
uvicorn lingyi.api.app:app --reload --port 8000

# Streamlit 前端
streamlit run lingyi/ui/app.py

# 数据处理
python -m data_pipeline.ingest
python -m data_pipeline.ingest --mode mock

# 测试
pytest tests/ -v

# 安装
pip install -e ".[dev]"
```

## Key Configuration

| 变量 | 说明 | 默认值 |
|---|---|---|
| `RAG_MODE` | RAG 模式 | `mock` |
| `RAG_ENABLE_EVALUATION` | RAG 质量评估循环 | `false` |
| `EMBEDDING_MODE` | Embedding 模式 | `local` |
| `MODEL_NAME` | LLM 模型 | `qwen-max` |
| `LLM_TIMEOUT` | LLM API 超时（秒） | `120` |
| `LLM_MAX_RETRIES` | LLM API 重试次数 | `3` |

## Conventions

- Python 3.12, conda env `lingyi`
- Runtime data in `storage/` — never commit
- `.env` holds API keys — never commit
- All modules use `logger = logging.getLogger(__name__)`
- Dependencies injected via constructors, no global singletons
- Core layer does NOT import FastAPI or Streamlit

## Agent 工作流

```
START → reader → mem_recall → safety_guard → inquiry → 路由
                                                        ├─ "chat"     → END（普通对话）
                                                        ├─ "consult"  → END（追问返回，最多2轮）
                                                        ├─ "diagnose" → rag_search → diagnosis → treatment → writer → END
                                                        └─ END
```

关键设计：
- **问诊循环控制**: `intent="consult"` 时暂停图执行，返回追问给用户。`inquiry_count` 限制最多追问 2 次，之后强制进入诊断
- **安全拦截**: `safety_guard` 使用关键词预检 + LLM 审查，拦截十八反十九畏配伍禁忌
- **意图重置**: 每次新消息时重置 `intent_type="chat"`，防止 checkpointer 中的旧状态影响路由
- **回复提取**: 从消息列表中取最后一条 `type=ai` 的消息，而非 `messages[-1]`（可能是用户消息）

## 安全机制

- `SafetyGuardSkill`: 前置拦截，检测用户输入中的配伍禁忌意图
- `SafetyEngine`: 规则引擎，十八反 6 条 + 十九畏 12 条
- 处方安全校验: `treatment` 节点生成处方后自动校验，不通过则要求 LLM 重写
- 安全拦截后 `intent_type` 设为 `"safety_rejected"`，图直接跳到结束

## LangChain / LangGraph 开发准则

**必须遵守**：所有涉及 LangChain / LangGraph 的开发，必须先查阅对应版本的官方文档，确认 API 签名和用法后再编写代码。不得凭记忆或猜测使用 API。

- **LangChain 文档**: https://docs.langchain.com/oss/python/
- **LangGraph 文档**: https://docs.langchain.com/oss/python/langgraph/
- **ChatOpenAI 参考**: https://docs.langchain.com/oss/python/integrations/chat/openai

关键规则：
1. `ChatOpenAI` 的超时参数是 `timeout`（不是 `request_timeout`），重试参数是 `max_retries`
2. LangGraph 流式输出使用 `graph.astream(stream_mode="messages")` 而非 `astream_events`
3. `AsyncSqliteSaver` 使用 `AsyncSqliteSaver(aiosqlite.connect(path))` 构造（`from_conn_string` 返回 async context manager，不能直接传给 `compile()`）
4. 优先使用 LangChain 内置的 `JsonOutputParser`、`ChatPromptTemplate` 等组件，不重复造轮子
5. 优先使用 LangGraph 内置的 `astream` 流式接口，不在 WebSocket 中用 `ainvoke` 阻塞等待
