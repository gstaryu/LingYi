# 全新克隆可运行性验证报告

> 验证日期：2026-11-02
> 验证对象：`https://github.com/gstaryu/LingYi.git` master 分支 `79f42ca`
> 验证方式：**换目录 + 换 conda 环境**，完全按 README 第一次上手，代码零修改（仅写 `.env`）

---

## 一、结论

**核心功能可跑通**：全新环境 `pip install -e ".[dev]"` + `npm ci` 后，后端启动、注册登录、普通对话、中医辨证开方、多智能体会诊、前端页面与 API 反代全部正常。

**但存在 4 个「静默降级」缺陷**：RAG 混合检索、MCP 服务端、web_search 工具在全新安装下**不报错地失效**，用户与开发者都不会察觉。另有 2 处 README 指导的命令在 clone 后必然失败。

---

## 二、验证环境

| 项 | 值 |
|---|---|
| 克隆目录 | `D:\PycharmProjects\LingYi-fresh-clone` |
| Python 环境 | 新建 `conda create -n lingyi_verify python=3.12`（3.12.16） |
| 主机 | Windows 11，Node v24.16.0，**无 NVIDIA GPU** |
| 克隆结果 | commit `79f42ca`，工作区干净，`.git` 86 MB |
| 后端安装 | `pip install -e ".[dev]"` 成功，**533 s**，装 200+ 包（torch 2.15.0 / chromadb 1.5.9 / langchain 1.4.7 / langgraph 1.2.19） |
| 前端安装 | `npm ci` 成功，**228 s**，783 包；`npm audit` 报 **2 critical / 16 high / 24 moderate / 1 low** |
| 磁盘占用 | 克隆目录 735 MB（其中 `node_modules` 545 MB） |

---

## 三、通过项（实测）

| 项 | 结果 |
|---|---|
| 后端启动 `/api/health` | 200 `{"status":"ok","version":"2.0.0","rag_mode":"mock"}` |
| 注册 / 登录 / JWT | 通过 |
| `chat` 意图对话 | 6.6 s |
| `diagnose`（workflow） | 33.0 s，输出归脾汤加减完整处方 |
| `diagnose`（multiagent） | 124.3 s，并行专家会诊正常 |
| 前端 Next.js 16.2.10 | `Ready in 4.9s`，首页 200（13 KB），`/api` 反代 200 |
| 无 GPU 时的 Embedding | 自动回退 CPU（见 `lingyi/models/local.py`），未崩溃 |
| 知识库免初始化 | `storage/patient_profiles.db` 随仓库分发，启动即可用 |

---

## 四、问题清单

### P0 — 静默降级（功能失效但不报错）

#### 1. `rank_bm25` 未声明依赖 → chroma 模式混合检索整体失效

- **位置**：`lingyi/rag/chroma.py:103` `from rank_bm25 import BM25Okapi`
- **现象**：`RAG_MODE=chroma` 启动正常、接口 200、照常出方，但日志里只有一行：
  ```
  ERROR | lingyi.agent.skills.rag_search | RAG 检索失败: No module named 'rank_bm25'
  ```
- **影响**：README 主打的「ChromaDB 向量 + BM25 的 RRF 混合融合」在全新安装下**完全用不上**，退化成无检索开方。使用者看不到任何错误，只会觉得「RAG 好像没什么用」。
- **修复**：`pyproject.toml` 补 `rank_bm25>=0.2`。

#### 2. `mcp` 未声明依赖 → MCP 服务端无法启动

- **位置**：`lingyi/mcp/server.py:23` `from mcp.server.fastmcp import FastMCP`
- **现象**：
  ```
  ModuleNotFoundError: No module named 'mcp'
  ```
- **影响**：README 特性「MCP 双向 · 暴露 5 只读工具」对使用者不可用。
- **修复**：补 `mcp>=1.0`。

#### 3. `langchain-mcp-adapters` 未声明依赖 → web_search 工具整条链路失效

- **位置**：`lingyi/tools/web_search.py:177`
- **现象**：每次启动固定两条日志，工具数从 8 降到 7：
  ```
  WARNING | lingyi.tools.web_search | 加载 langchain-mcp-adapters 失败，将尝试回退: No module named 'langchain_mcp_adapters'
  INFO    | lingyi.tools.factory | web_search 工具未注入，工具集共 7 个
  ```
- **修复**：补 `langchain-mcp-adapters>=0.1`，或明确在 README 标注为可选依赖。

#### 4. 硬编码作者本机绝对路径，且配置项未暴露

- **位置**：`lingyi/config.py:231`、`config.py:235`，`lingyi/tools/web_search.py:165-171`（兜底默认值同样硬编码）
  ```python
  rivalsearch_mcp_command: str = "C:/Users/start/mcp-servers/RivalSearchMCP/.venv/Scripts/python.exe"
  rivalsearch_mcp_script: str  = "C:/Users/start/mcp-servers/RivalSearchMCP/server.py"
  ```
- **现象**：`.env.example` 中**没有** `RIVALSEARCH_MCP_COMMAND` / `RIVALSEARCH_MCP_SCRIPT` / `WEB_SEARCH_ENABLED` 三个键，使用者完全不知道有这些配置。
- **影响**：即使装上适配器，别人也指向不到自己的 MCP 服务，web_search 仍然是坏的。本次验证因跑在作者本机（路径恰好存在）而**未暴露**，但这正是「只有作者机器能正常工作」的典型。
- **修复**：默认值改为空字符串 + 显式校验；三键补进 `.env.example`；路径建议改为相对仓库或由使用者注入。

### P1 — 文档与仓库内容失真

#### 5. `tests/`、`evaluation/` 被 gitignore，但 README 指导用户运行

- **位置**：`.gitignore:47`（`tests/`）、`.gitignore:64`（`evaluation/`）
- **现象**：clone 后两个目录不存在（本地分别有 58 / 11 个 py 文件），README:182-192 的命令必然失败：
  ```
  ERROR: file or directory not found: tests/
  ModuleNotFoundError: No module named 'evaluation'
  ```
- **加重**：`docs/evaluation_report.md`（六维评测结果）却已提交 —— 读者能看到报告，却无法复现任何一条。
- **修复**：二选一 —— 要么把 `tests/` 与 `evaluation/` 入库；要么从 README 删除「测试与评测」章节并注明「开发产物，不随仓库分发」。

#### 6. Node.js 版本要求偏低

- **位置**：`README.md:82` 写 `Node.js 18+`；`frontend/package.json:19` 为 `next@16.2.10`
- **影响**：Next.js 16 需 Node ≥ 20.9；`package.json` 无 `engines` 字段，Node 18 用户会在 `npm ci`/`next dev` 阶段才撞墙。
- **修复**：README 改 `Node.js 20.9+`，并在 `package.json` 加 `"engines": {"node": ">=20.9"}`。

### P2 — 代码质量（与克隆无关，原项目同样存在）

#### 7. 引用了从未创建的 prompt 文件

- **位置**：`lingyi/agent/skills/profile_writer.md` —— 原项目与 clone 中**都不存在**（该目录只有 9 个 md：diagnosis / inquiry / rag_grader / rag_rewrite / rag_search / reader / safety_guard / treatment / writer）
- **现象**：每次启动固定 WARNING：
  ```
  WARNING | lingyi.agent.skills.base | 未找到 prompt 文件: ...\lingyi\agent\skills\profile_writer.md
  ```
- **修复**：补文件，或删掉该查找逻辑。

#### 8. 内部结构化输出泄露到用户可见回复

- **现象**：`workflow` 与 `multiagent` 两种模式**均复现** —— 回复正文末尾多出：
  ```` ```json {"herb_names": ["黄芪", "党参", ...]} ``` ````
- **影响**：前端按 Markdown 渲染，患者会直接看到机读 JSON 代码块。
- **修复**：`writer` 节点剥离尾部 json 块，或用结构化输出字段承载而非拼进正文。

#### 9. Windows 控制台中文日志乱码

- **现象**：即使 `PYTHONUTF8=1`，PowerShell 抓取到的日志仍是 `鐏靛尰 API 鍚姩涓?` 形态（UTF-8 被按 GBK 解码）。
- **现状**：仓库有 `start.ps1` 与 `start-gbk.ps1` 两个脚本，README 未说明何时用哪个。
- **修复**：README 补一句 Windows 终端编码说明，或在 `logging.py` 统一 `encoding="utf-8"` 写文件日志。

### P3 — 工程规范

#### 10. 无依赖锁文件

- `pyproject.toml` 全部为 `>=` 下界（`langchain>=1.0`、`langgraph>=1.0`、`chromadb>=0.6` …），无 `requirements.txt` / `uv.lock`。
- 本次实际装到 langchain 1.4.7 / langgraph 1.2.19 / chromadb 1.5.9 / torch 2.15.0 —— 这些数字会随时间漂移，"今天能装、明天装不上"的风险实存。

#### 11. 二进制运行时数据入库，且与实际数据静默分叉

| 文件 | 大小 | 说明 |
|---|---|---|
| `storage/checkpoints_eval.db` | 31 MB | 评测产物，不应入库 |
| `storage/checkpoints.db` | 16.7 MB | LangGraph 会话检查点 |
| `storage/patient_profiles.db` | 10 MB | 知识库 + 用户（**"免初始化启动"依赖它**） |

- 合计约 58 MB，是 `.git` 86 MB 的主要构成。
- **隐蔽点**：SQLite 写入落在被忽略的 `storage/*.db-wal` / `-shm`，所以跑完应用 `git status` 依然干净；但仓库里的 `.db` 会与实际运行数据**静默分叉**，提交时也不会更新。
- 与 `CLAUDE.md`「Runtime data in `storage/` — never commit」自相矛盾。

#### 12. 分发的 DB schema 落后于代码

- **现象**：首次启动即执行迁移：
  ```
  INFO | lingyi.storage.sqlite | 迁移：profiles 表新增 birth_year 列
  INFO | lingyi.storage.sqlite | 迁移：profiles 表新增 gender 列
  INFO | lingyi.storage.sqlite | 迁移：profiles 表新增 medical_history 列
  ```
- **影响**：不致命（迁移代码能兜住），但说明仓库里的 `.db` 不是从当前 schema 生成的。

---

## 五、修复优先级建议

| 优先级 | 动作 |
|---|---|
| **P0** | 补 `rank_bm25` / `mcp` / `langchain-mcp-adapters` 到 `pyproject.toml`；`RIVALSEARCH_MCP_*` 去硬编码并写入 `.env.example` |
| **P1** | 决定 `tests/` `evaluation/` 是否入库（二者择一，勿维持"文档有、仓库无"）；Node 版本改 20.9+ |
| **P2** | 删除 `checkpoints_eval.db`；为 `storage/*.db` 加 `.gitattributes` `-diff`；评估是否改用首次启动自动 seed 取代二进制入库 |
| **P3** | 修 `profile_writer.md`、剥离 JSON 泄露、补锁文件、README 补 Windows 编码说明 |

---

## 六、复现命令

```powershell
# 1) 克隆与环境
git clone https://github.com/gstaryu/LingYi.git D:\PycharmProjects\LingYi-fresh-clone
conda create -n lingyi_verify python=3.12 -y

# 2) 安装
cd D:\PycharmProjects\LingYi-fresh-clone
conda run -n lingyi_verify python -m pip install -e ".[dev]"
cd frontend; npm ci; cd ..

# 3) 配置（仅复制模板即可启动，LLM 调用需填真实 Key）
Copy-Item .env.example .env

# 4) 启动
$env:PYTHONUTF8="1"
conda run -n lingyi_verify uvicorn lingyi.api.app:app --port 8010
cd frontend; $env:BACKEND_URL="http://localhost:8010"; npm run dev -- -p 3010

# 5) 复现问题 1/2/3
conda run -n lingyi_verify pytest tests/ -q                            # P1-5
conda run -n lingyi_verify python -m evaluation.runner --only safety   # P1-5
conda run -n lingyi_verify python -m lingyi.mcp.server                 # P0-2
$env:RAG_MODE="chroma"; conda run -n lingyi_verify uvicorn lingyi.api.app:app --port 8011
#   然后发一条诊断消息，观察日志 "RAG 检索失败: No module named 'rank_bm25'"
```

---

## 七、验证残留

- 克隆目录 `D:\PycharmProjects\LingYi-fresh-clone`（735 MB）与 conda 环境 `lingyi_verify` 均保留，便于复现；确认后可直接删除。
- 原项目工作区未受影响（仅新增本报告）。

---

## 八、2026-11-03 修复与验证

### 已修复

| # | 问题 | 改动 |
|---|---|---|
| 1 | `rank_bm25` 未声明 | `pyproject.toml` 增加 `rank_bm25>=0.2` |
| 2 | `mcp` 未声明 | `pyproject.toml` 增加 `mcp>=1.0` |
| 3 | `langchain-mcp-adapters` 未声明 | `pyproject.toml` 增加 `langchain-mcp-adapters>=0.1` |
| 4 | MCP 路径硬编码 `C:/Users/start/...` | `lingyi/config.py` 默认值改为空串；`tools/web_search.py` 未配置时跳过，日志改为明确说明（不再是误导性的"适配器加载失败"警告） |
| 5 | 配置项未暴露 | `.env.example` 增加 `WEB_SEARCH_ENABLED` / `RIVALSEARCH_MCP_COMMAND` / `RIVALSEARCH_MCP_SCRIPT` / `WEB_SEARCH_FALLBACK_TO_DDGS` |
| 6 | RAG 日志虚报召回数 | `skills/rag_search.py` 改为打印实际召回条数（原为配置值 `recall_k`，恒显示 15，掩盖了空库问题） |
| 7 | `profile_writer.md` 缺失告警 | `memory/profile_writer.py` 覆盖 `_load_prompt` 返回空串 |
| 8 | 回复末尾泄露 herb_names JSON | 新增 `text_utils.strip_herb_json_block`，在 `treatment` / `graph_multiagent` 的消息构造与 `chat.py` 的响应提取处剥离；`treatment_plan` 保留原文供 SafetyEngine 解析 |
| 9 | README Node 版本偏低 | 18+ → 20.9+ |

**已知局限**：SSE 流式传输按 token 逐块推送，JSON 块仍会在流中实时出现；剥离只作用于最终消息与历史读取。

### 新增发现：仓库内的 ChromaDB 不可用

- **现象**：`storage/chroma_db/c7df8ba6-.../data_level0.bin`（3.9 MB）在仓库中，但打开后 `collection.count() == 0`。
- **根因**：向量正文与索引存放在 `chroma.sqlite3`，该文件在 **2026-06-27 21:42 的 commit `23923e6`「重构整个项目」中被删除**，此后未补回。2026-09-09 的 `24e9107`「上传数据库文件」只补了段目录，段文件因此成为孤儿。
- **修复**：用当前切分器重建（`python -m data_pipeline.ingest --mode chroma`，1537 条），提交 `chroma.sqlite3`（15.5 MB）与新段目录 `c1c74810-...`（4.6 MB），删除孤儿段 `c7df8ba6-...`。
- **验证**：`hybrid_search("失眠 入睡困难 白天乏力", n=5)` 命中 5 条真实正文（含《灵枢》「病而不得卧」、《伤寒论》太阳病篇），质量优于旧库只命中章节标题碎片。

### 仍未处理

- `tests/` 与 `evaluation/` 是否入库（需产品决策）
- SSE 流中的 JSON 块实时泄露
- `storage/checkpoints_eval.db`（31 MB 评测产物）仍在版本库
- 依赖未锁定（无 lock 文件）

