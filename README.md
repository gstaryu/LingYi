# 灵医 LingYi · 中医智能诊疗系统

> 基于多智能体架构的中医辨证论治辅助系统。按"理、法、方、药"体系，通过问诊-辨证-方剂-本草的并行专家会诊，给出结构化的辨证结论与处方建议，并内置十八反十九畏配伍安全校验。

---

## ✨ 核心特性

- **多智能体会诊**：辨证、方剂、本草三位专家并行出诊，综合节点汇总结论；可选对抗式安全审查者做处方复核。
- **双工作流模式**：`workflow`（固定流程，轻量快速）与 `multiagent`（并行专家会诊 + 对抗审查）一键切换。
- **安全双重防御**：前置 `safety_guard` 拦截 + 确定性 `SafetyEngine`（十八反 6 条 / 十九畏 12 条）硬校验，处方生成后自动核查配伍禁忌。
- **RAG 经典检索**：ChromaDB 向量检索 + BM25 字符级检索的 RRF 混合融合，支持 Qwen3-Embedding 与可选 CrossEncoder 重排。
- **画像记忆**：SQLite 持久化用户体质、过敏史、诊疗记录；每轮回话自动加载画像，会诊结束写入更新。
- **MCP 双向**：既作为 MCP 服务端暴露 5 只读工具，又可作为消费者复用外部 MCP（如 web_search）。
- **结构化知识库**：本草 / 方剂 / 禁忌三库（33 本草 / 22 方剂 / 38 禁忌），幂等种子脚本一键入库。
- **流式前端**：Next.js + React，SSE 流式输出，会诊阶段时间线、处方卡片、过敏史编辑。

---

## 🧱 技术栈

| 层 | 技术 |
|---|---|
| Agent 编排 | LangGraph 1.x（StateGraph / Send 并行 / Checkpointer） |
| LLM 框架 | LangChain 1.x（ChatOpenAI / create_agent / 结构化输出） |
| LLM | Qwen3 系列（DashScope），按角色可配不同模型 |
| 后端 | FastAPI + Uvicorn，JWT 鉴权，SSE / WebSocket 流式 |
| 前端 | Next.js 16 + React 19 + Tailwind v4 + @base-ui/shadcn |
| 向量库 | ChromaDB（生产）/ Mock（开发） |
| 嵌入 | Qwen3-Embedding-0.6B（本地 HuggingFace / 在线 DashScope） |
| 持久化 | SQLite（aiosqlite 异步） |
| 安全 | SafetyEngine 规则引擎 + 对抗审查者 |

---

## 📁 项目结构

```
LingYi/
├── lingyi/                  # 主包
│   ├── agent/               # LangGraph 图 + 技能节点 + 专家 + 记忆
│   │   ├── graph.py             # workflow 模式图工厂（默认）
│   │   ├── graph_multiagent.py  # multiagent 模式图工厂
│   │   ├── skills/              # inquiry / diagnosis / treatment / safety_guard / rag_search
│   │   ├── specialists/         # 辨证 / 方剂 / 本草 专家
│   │   ├── safety_reviewer.py   # 对抗安全审查者
│   │   └── memory/              # recall / profile_writer / summarizer
│   ├── tools/               # 7 个领域工具（DI 工厂）
│   ├── knowledge/           # 结构化知识库模型
│   ├── rag/                 # RAG（mock/chroma + reranker + BM25 混合）
│   ├── safety/              # 十八反十九畏规则引擎
│   ├── storage/             # SQLite 持久化
│   ├── mcp/                 # MCP 服务端（FastMCP stdio）
│   ├── api/                 # FastAPI 后端
│   └── config.py            # pydantic-settings 配置
├── frontend/               # Next.js 前端
├── data_pipeline/          # TCM 数据处理（ingest + seed_knowledge）
├── tests/                  # pytest 测试套件
└── docs/                   # 项目文档
```

详细架构见 [docs/architecture.md](docs/architecture.md)。

---

## 🚀 快速开始

### 环境要求

- Python 3.12（conda 环境名 `lingyi`）
- Node.js 18+（前端）
- DashScope API Key（模型与嵌入）

### 1. 安装

```bash
# 后端
conda activate lingyi
pip install -e ".[dev]"

# 前端
cd frontend
npm install
```

### 2. 配置

在项目根目录创建 `.env`（不提交）：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxx
MODEL_NAME=qwen-max
RAG_MODE=mock                 # mock（开发）/ chroma（生产）
EMBEDDING_MODE=local          # local（HuggingFace）/ online（DashScope）
AGENT_MODE=multiagent         # workflow / multiagent
```

完整配置项见 [docs/deployment.md](docs/deployment.md)。

### 3. 初始化知识库

```bash
# 结构化知识库（本草/方剂/禁忌，幂等）
python -m data_pipeline.seed_knowledge

# RAG 经典语料入库（chroma 模式）
python -m data_pipeline.ingest --mode chroma
```

### 4. 启动服务

```bash
# 后端（UTF-8 安全启动脚本）
./scripts/dev_backend.ps1
# 或
uvicorn lingyi.api.app:app --reload --port 8000

# 前端
cd frontend && npm run dev
```

打开 http://localhost:3000，注册账号即可开始问诊。

### 5. 测试

```bash
pytest tests/ -v          # 后端
cd frontend && npm run test   # 前端
```

---

## 🩺 Agent 工作流

灵医支持两种工作流，通过 `AGENT_MODE` 切换：

**workflow 模式**（默认，轻量）：
```
START -> reader -> mem_recall -> safety_guard -> inquiry -> 路由
   ├─ chat/consult -> summarize -> writer -> END
   └─ diagnose -> rag_search -> diagnosis -> treatment -> safety_check -> writer -> END
```

**multiagent 模式**（并行专家会诊 + 对抗审查）：
```
START -> reader -> mem_recall -> safety_guard -> inquiry -> 路由
   ├─ chat/consult -> summarize -> writer -> END
   └─ diagnose -> dispatch -> [辨证 | 方剂 | 本草] 并行 -> synthesis
                  -> reviewer -> safety_check -> summarize -> writer -> END
```

- **工具 = Agent 可选择做的事**（LLM 自主决定）：检索经典、查药材、查方剂、web_search 等。
- **图边 = 必须永远发生的事**（不可省略）：safety_guard、SafetyEngine、summarizer、reader、profile_writer。
- 处方生成后经 SafetyEngine 确定性校验，不通过则反馈要求重写。

详见 [docs/agent.md](docs/agent.md)。

---

## 🔒 安全机制

| 层 | 职责 |
|---|---|
| `SafetyGuardSkill` | 前置拦截，关键词预检 + LLM 审查用户输入中的禁忌意图 |
| `SafetyEngine` | 确定性规则引擎，十八反 6 条 + 十九畏 12 条，处方生成后硬校验 |
| `SafetyReviewerAgent` | 对抗式批评者（multiagent），智能审查处方，不通过则回综合节点重生成 |
| `SAFETY_FAIL_MODE` | 前置审查 LLM 异常时策略：`closed`（拒绝，默认）/ `open`（放行） |

所有处方建议末尾声明：**孕妇、哺乳期女性使用前需咨询专业中医师**。本系统输出仅供参考，不能替代执业中医师面诊。

---

## 📚 文档索引

| 文档 | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 系统架构、分层、依赖注入、状态流 |
| [docs/agent.md](docs/agent.md) | Agent 工作流、专家会诊、安全审查、记忆、工具、MCP |
| [docs/api.md](docs/api.md) | REST API 参考（认证、会话、流式、画像） |
| [docs/rag.md](docs/rag.md) | RAG 子系统、混合检索、重排 |
| [docs/deployment.md](docs/deployment.md) | 部署、配置项、环境变量 |
| [docs/data_pipeline.md](docs/data_pipeline.md) | 数据处理与知识库种子 |
| [docs/testing.md](docs/testing.md) | 测试体系与运行 |

---

## ⚠️ 免责声明

灵医是中医诊疗辅助系统，所有输出（辨证、处方、用药建议）仅供学习与研究参考，**不构成医疗建议**，不能替代执业中医师面诊。请勿据此自行抓药。处方中涉及毒性药材（如附子、半夏）须严格遵医嘱炮制与使用。
