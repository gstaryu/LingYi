# 🎋 灵医 (LingYi) - 中医诊疗多智能体系统

![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-1.2-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-后端-009688.svg)
![Next.js](https://img.shields.io/badge/Next.js-16-前端-black.svg)

**灵医 (LingYi)** 是基于 **LangGraph** 的中医诊疗多智能体系统，按"**理法方药**"推演：问诊 -> 辨证（理法）-> 处方（方药）+ 配伍禁忌校验。架构为 **FastAPI 后端 + Next.js 前端**，前后端分离，SSE 流式输出。

---

## ✨ 核心特性

- 🩺 **理法方药流程**：多轮问诊 -> 辨证（病机/治则）-> 处方（方剂/药物），结构化输出
- 💬 **SSE 流式输出**：前端逐字显示理法方药，可中途停止
- 📚 **按需 RAG**：根据辨证动态检索中医古籍
- 🛡️ **双重安全护栏**：前置意图拦截（配伍禁忌请求）+ 后置处方校验（十八反/十九畏）
- 👤 **用户画像**：按用户名持久化体质、过敏史，跨会话共享，诊疗后自动更新
- 📎 **文件上传**：病历 PDF/DOCX/TXT 解析辅助诊断
- 🔐 **JWT 认证**：注册/登录/会话隔离
- 💾 **会话持久化**：LangGraph checkpointer 保存对话历史，支持多会话切换

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────┐
│          Next.js 16 前端 (:3000)            │
│  React 19 + shadcn/ui + Tailwind + SSE      │
└──────────────────┬──────────────────────────┘
                   │ HTTP / SSE（JWT Bearer）
┌──────────────────▼──────────────────────────┐
│          FastAPI 后端 (:8000)               │
│  /api/chat(流式) · /threads · /profiles     │
│  · /upload · /login · /register             │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│      Core（纯 Python，不依赖 Web 框架）      │
│  agent/(LangGraph 图+技能) · rag/ · safety/ │
│  storage/(SQLite) · models/ · parsers/      │
└─────────────────────────────────────────────┘
```

**Agent 工作流**：
```
START -> reader -> mem_recall -> safety_guard -> inquiry -> 路由
  ├ chat/consult -> END（普通对话/追问）
  ├ safety_rejected -> END（安全拦截）
  └ diagnose -> rag_search -> diagnosis(理法) -> treatment(方药) -> writer -> END
```

---

## 🚀 快速开始

### 一键启动（Windows PowerShell）

```powershell
.\start.ps1
```

自动打开两个窗口分别运行后端与前端。

### 手动启动

**前置**：Python 3.12（conda 环境 `lingyi`）、Node.js 18+。

```bash
# 1. 后端
conda activate lingyi
pip install -e ".[dev]"
cp .env.example .env   # 填入 OPENAI_API_KEY / DASHSCOPE_API_KEY
uvicorn lingyi.api.app:app --port 8000

# 2. 前端（另开终端）
cd frontend
npm install
npm run dev
```

打开 http://localhost:3000 -> 注册 -> 对话。

### 配置（`.env`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `OPENAI_API_KEY` / `DASHSCOPE_API_KEY` | LLM API Key（OpenAI 兼容） | - |
| `MODEL_NAME` | LLM 模型名 | `qwen-max` |
| `RAG_MODE` | RAG 模式（`mock`/`chroma`） | `mock` |
| `EMBEDDING_MODE` | Embedding 模式（`local`/`online`） | `local` |
| `LLM_TIMEOUT` | LLM 超时（秒） | `120` |

前端直连后端：`frontend/.env.local` 的 `NEXT_PUBLIC_API_URL`（默认 `http://localhost:8000`）。

---

## 🚢 部署

### 开发模式

```bash
# 一键启动（自动开两个进程）
./start.sh          # Linux/macOS/Git Bash
.\start.ps1         # Windows PowerShell
```

或手动分两个终端：后端 `uvicorn lingyi.api.app:app --port 8000`，前端 `cd frontend && npm run dev`。

### 生产部署

**后端**（uvicorn/gunicorn）：
```bash
conda activate lingyi
pip install -e ".[dev]"
uvicorn lingyi.api.app:app --host 0.0.0.0 --port 8000
# 或 gunicorn -k uvicorn.workers.UvicornWorker -w 4 lingyi.api.app:app
```

**前端**（Next.js 静态/Node 服务）：
```bash
cd frontend
npm install
npm run build       # 生产构建
npm run start       # 启动生产服务（默认 :3000）
# 生产环境把 NEXT_PUBLIC_API_URL 指向后端公网地址
```

**注意**：
- 生产环境务必更换 `JWT_SECRET_KEY`（默认是开发密钥）。
- 后端 CORS 默认 `*`，生产建议限定前端域名（`lingyi/api/app.py`）。
- RAG 生产模式切 `RAG_MODE=chroma` 并运行 `python -m data_pipeline.ingest --mode chroma` 建索引。
- 运行时数据（SQLite、上传文件、checkpoints）在 `storage/`，注意备份。

---

## 🧪 测试

```bash
conda activate lingyi
pytest tests/ -v          # 后端（含 API/Skill/RAG/Safety/Storage，无需真实 API）
cd frontend && npm run build   # 前端构建
```

---

## 📁 目录结构

```
LingYi/
├── lingyi/                  # 后端主包
│   ├── agent/               # LangGraph 图 + skills/ + memory/
│   ├── api/                 # FastAPI 路由（chat/threads/profiles/upload/auth）
│   ├── rag/                 # RAG（mock/chroma/reranker）
│   ├── safety/              # 十八反十九畏引擎
│   ├── storage/             # SQLite（用户/画像/线程/checkpointer）
│   ├── models/              # LLM/Embedding 抽象
│   └── parsers/             # 文件解析（PDF/DOCX/TXT）
├── frontend/                # Next.js 16 前端
│   └── src/{app,components,hooks,lib,stores}
├── data_pipeline/           # TCM 古籍切分入库
├── tests/                   # pytest 测试套件
├── docs/                    # 文档
├── start.ps1                # 一键启动脚本
└── TCM_data/                # 中医古籍原始数据
```

---

## ⚠️ 免责声明

本项目仅供技术探索与学术研究，**不具备临床执业资格**。所有处方建议仅供参考，切勿自行抓药，如有身体不适请就医。

## 📄 License

[MIT License](LICENSE)
