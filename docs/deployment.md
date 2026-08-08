# 部署指南

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 11 / Linux / macOS |
| Python | 3.12 |
| Conda 环境 | `lingyi` |
| Node.js | 18+（前端） |
| GPU | 可选（本地 Embedding 模型加速，无 GPU 时自动回退 CPU） |

## 安装

### 后端

```bash
# 克隆项目
git clone <repository-url>
cd LingYi

# 创建 conda 环境
conda create -n lingyi python=3.12
conda activate lingyi

# 安装依赖
pip install -e ".[dev]"
```

### 前端

```bash
cd frontend
npm install
```

## 配置

### .env 文件

在项目根目录创建 `.env` 文件（不提交到版本控制），填入必要的 API Key 和配置：

```env
# LLM
DASHSCOPE_API_KEY=sk-your-api-key-here
MODEL_NAME=qwen-max

# RAG
RAG_MODE=mock
EMBEDDING_MODE=local

# Agent
AGENT_MODE=workflow

# 安全
SAFETY_FAIL_MODE=closed

# 追踪
ENABLE_TRACING=false

# 网络搜索
WEB_SEARCH_ENABLED=true
```

### 配置项参考

以下配置项均可通过环境变量或 `.env` 文件覆盖，均定义在 `lingyi/config.py: Settings`：

#### LLM 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | （空） | 阿里云 DashScope API Key |
| `OPENAI_API_KEY` | （空） | OpenAI 兼容 API Key（备用） |
| `OPENAI_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI 兼容 API Base URL |
| `MODEL_NAME` | `qwen-max` | LLM 模型名称 |
| `LLM_TEMPERATURE` | `0.7` | LLM 温度参数 |
| `LLM_TIMEOUT` | `120` | LLM API 超时时间（秒） |
| `LLM_MAX_RETRIES` | `3` | LLM API 最大重试次数 |
| `LLM_SPECIALIST_MAX_RETRIES` | `1` | 专家/综合/审查者 LLM 最大重试次数 |

#### 多智能体专家模型

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MODEL_NAME_BIANZHENG` | （空） | 辨证专家模型名（留空回退到 `MODEL_NAME`） |
| `MODEL_NAME_FANGJI` | （空） | 方剂专家模型名 |
| `MODEL_NAME_BENCAO` | （空） | 本草专家模型名 |

#### Embedding 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EMBEDDING_MODE` | `local` | Embedding 模式: local / online |
| `EMBEDDING_MODEL_NAME` | `Qwen/Qwen3-Embedding-0.6B` | 本地 Embedding 模型名称 |
| `EMBEDDING_ONLINE_MODEL_NAME` | `text-embedding-v4` | 在线 DashScope Embedding 模型名 |
| `EMBEDDING_QUERY_PROMPT_NAME` | （空） | 查询嵌入 prompt 名称（Qwen3 需设为 `query`） |
| `EMBEDDING_DEVICE` | `cuda` | Embedding 设备: cuda / cpu |

#### RAG 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `RAG_MODE` | `mock` | RAG 模式: mock / chroma |
| `RAG_RECALL_K` | `15` | 粗排召回 Top-K |
| `RAG_RERANK_K` | `5` | 精排截取 Top-K |
| `RAG_SCORE_THRESHOLD` | `0.7` | RAG 质量及格分数线 |
| `RAG_MAX_RETRIES` | `3` | RAG 搜索最大重试次数 |
| `RAG_ENABLE_EVALUATION` | `false` | 是否启用 RAG 质量评估循环 |
| `RERANK_MODEL_NAME` | `BAAI/bge-reranker-v2-m3` | Cross-Encoder 重排模型名称 |

#### Agent 工作流配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AGENT_MODE` | `workflow` | Agent 模式: workflow / multiagent |
| `MAX_FOLLOWUPS` | `1` | 最大追问轮数 |
| `SAFETY_MAX_RETRIES` | `3` | 安全校验最大重试次数 |
| `REVIEWER_MAX_RETRIES` | `2` | 对抗审查者最大重试次数 |
| `SAFETY_FAIL_MODE` | `closed` | 前置安全审查 LLM 异常策略: closed / open |
| `TOKEN_COMPRESSION_THRESHOLD` | `8000` | 上下文压缩触发阈值（字符数） |

#### 认证与网络

| 变量 | 默认值 | 说明 |
|---|---|---|
| `JWT_SECRET_KEY` | `lingyi-dev-secret-change-in-production` | JWT 签名密钥（生产必须更换） |
| `JWT_ALGORITHM` | `HS256` | JWT 签名算法 |
| `JWT_EXPIRE_MINUTES` | `1440` | JWT Token 有效期（分钟） |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:8501` | 允许的 CORS 来源（逗号分隔） |

#### 追踪与搜索

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ENABLE_TRACING` | `false` | 是否启用 LangSmith 链路追踪 |
| `LANGSMITH_API_KEY` | （空） | LangSmith API Key |
| `LANGSMITH_PROJECT` | `lingyi` | LangSmith 项目名 |
| `WEB_SEARCH_ENABLED` | `true` | 是否启用 web_search 工具 |

## 启动

### 后端

**方式一：开发脚本（推荐，UTF-8 安全）**

```powershell
.\scripts\dev_backend.ps1
```

`scripts/dev_backend.ps1` 脚本：
- 设置 `PYTHONUTF8=1`（Python 强制 UTF-8 模式）
- 设置 `AGENT_MODE=multiagent`（多智能体模式）
- 切换 Windows 控制台代码页为 UTF-8（65001）
- 激活 conda 环境
- 启动 `uvicorn lingyi.api.app:app --port 8000 --log-level info`

**方式二：直接启动**

```bash
conda activate lingyi
uvicorn lingyi.api.app:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm run dev
```

前端默认运行在 `http://localhost:3000`。

## 初始化

### 知识库种子数据

结构化知识库（本草/方剂/禁忌）种子数据，写入 `storage/patient_profiles.db`：

```bash
python -m data_pipeline.seed_knowledge
```

此操作幂等（使用 `INSERT ON CONFLICT DO UPDATE`），可重复运行。

### RAG 数据入库

将中医古籍文本切分并嵌入 ChromaDB：

```bash
# ChromaDB 入库（需 embedding 模型）
python -m data_pipeline.ingest --mode chroma

# 或仅生成 mock 数据（本地开发）
python -m data_pipeline.ingest --mode mock
```

**HuggingFace 镜像**：国内下载模型缓慢时，设置 `HF_ENDPOINT=https://hf-mirror.com`（默认）。镜像不可达时设为 `HF_ENDPOINT=https://huggingface.co`。

### MCP 服务端

启动 MCP stdio 服务（供 Claude Desktop 等外部客户端调用）：

```bash
python -m lingyi.mcp.server
```

## 运行时数据

所有运行时数据存储在 `storage/` 目录（不提交到版本控制）：

| 路径 | 说明 |
|---|---|
| `storage/patient_profiles.db` | SQLite 数据库（用户/画像/线程/herbs/formulas/contraindications） |
| `storage/checkpoints.db` | LangGraph 检查点数据库（会话状态持久化） |
| `storage/chroma_db/` | ChromaDB 持久化目录（向量索引） |
| `storage/uploads/` | 用户上传文件目录 |
| `storage/chunks/` | 数据切分 JSON 输出目录 |
| `storage/mock_rag_data.json` | Mock RAG 预设数据 |

## 生产部署注意事项

1. **JWT 密钥**：生产环境必须更换 `JWT_SECRET_KEY`
2. **CORS 来源**：通过 `CORS_ORIGINS` 环境变量设置允许的前端域名
3. **API Key**：确保 `DASHSCOPE_API_KEY` 已配置，否则 Agent 不会初始化（认证接口返回 503）
4. **Embedding 模式**：生产环境推荐 `EMBEDDING_MODE=online`（无需本地 GPU）或确保 GPU 可用
5. **RAG 模式**：生产环境使用 `RAG_MODE=chroma`，需先执行数据入库
6. **Agent 模式**：`AGENT_MODE=multiagent` 启用多智能体会诊（更高质量，更多 LLM 调用）
7. **追踪**：`ENABLE_TRACING=true` 启用 LangSmith 链路追踪，便于调试
