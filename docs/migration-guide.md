# 迁移指南 - LingYi 2.0 升级（2026-08）

本次升级含若干破坏性变更，部署前请按本指南调整环境与配置。

## 1. Embedding 模型切换（破坏性）

默认本地 Embedding 模型从 `BAAI/bge-m3` 改为 `Qwen/Qwen3-Embedding-0.6B`（1024 维，instruction-aware）。

**影响**：
- Qwen3-Embedding 查询侧必须用 `prompt_name="query"`（已由 factory 按模型名自动检测，无需手动配置）。
- 既有 ChromaDB 向量库是用旧模型嵌入的，**与新模型嵌入空间不兼容**，必须重新入库。

**迁移步骤**：
```bash
# 1. 删除旧向量库（旧嵌入空间已失效）
rm -rf storage/chroma_db

# 2. 用新模型重新入库
conda activate lingyi
python -m data_pipeline.ingest --mode chroma
```

**回退到 BGE-M3**（如需）：在 `.env` 设置
```
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_QUERY_PROMPT_NAME=
```

**online 模式**：DashScope 用 `text-embedding-v4`（`EMBEDDING_ONLINE_MODEL_NAME`），与本地模型名解耦。

## 2. ChromaDB 入库/查询嵌入空间修复（破坏性）

**问题**：此前 `ChromaRAGClient.add_documents` 用 `upsert(documents=...)` 不传向量，ChromaDB 以其默认 MiniLM 嵌入入库；而查询用注入的 embedding_model -> **入库与查询嵌入空间不一致，检索结果错误**。

**修复**：`add_documents` 现用注入的 embedding_model 生成向量后 `upsert(embeddings=...)`，确保同一空间。

**迁移**：同上，需重新入库（旧数据嵌入空间错误）。

## 3. Checkpointer 生命周期变更

- 检查点 SQLite 文件独立为 `storage/checkpoints.db`（此前混入 `patient_profiles.db`）。
- checkpointer 现由 FastAPI `lifespan` 创建并存入 `app.state.checkpointer`，应用关闭时关闭底层 aiosqlite 连接。
- `create_agent` 新增必填参数 `checkpointer`（不再内部创建）。

**影响**：直接调用 `create_agent` 的代码需传入 checkpointer。`storage/checkpoints.db` 为新文件，旧检查点（在 `patient_profiles.db` 中）不再读取。

## 4. WebSocket 鉴权（破坏性）

`WS /api/ws/chat` 不再使用 `default_user`，必须通过 query 参数鉴权：
```
ws://host:8000/api/ws/chat?token=<JWT>
```
无 token 或 token 无效 -> 连接被关闭（code 4401）。

## 5. CORS 白名单

`allow_origins` 由 `["*"]` 改为白名单（`*` 与 `allow_credentials=True` 冲突，被浏览器拒绝）。通过配置项控制：
```
CORS_ORIGINS=http://localhost:3000,http://localhost:8501
```
生产环境必须设置为实际前端域名（逗号分隔）。

## 6. 输入长度限制

API 请求体新增 `max_length` 约束：
- `ChatRequest.message` ≤ 10000 字符
- `ThreadCreate.title` / `ThreadRename.new_title` ≤ 100 字符
- `ChatRequest.files` ≤ 10 项

超限返回 422。

## 7. 依赖变更

- `pypdf2` -> `pypdf`（维护后继版，API 兼容；`from pypdf import PdfReader`）。
- 升级：pillow 12.3.0、gitpython 3.1.57、setuptools 83.0.0（修复 CVE）。
- **torch 2.12.1 的 PYSEC-2025-194 延后处理**：升级到 2.13.0 需 ~2GB 下载，且 torch 运行时不依赖 setuptools（仅元数据约束）。建议在确认 GPU/驱动兼容后单独升级：`pip install -U "torch>=2.13.0"`。

## 8. 配置项新增

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EMBEDDING_MODEL_NAME` | `Qwen/Qwen3-Embedding-0.6B` | 本地 Embedding 模型 |
| `EMBEDDING_ONLINE_MODEL_NAME` | `text-embedding-v4` | online 模式 DashScope 模型 |
| `EMBEDDING_QUERY_PROMPT_NAME` | (空，自动检测) | 查询嵌入 prompt 名 |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:8501` | CORS 白名单 |

## 9. 画像合并语义（行为修复）

修复画像被覆盖导致过敏史丢失的 Bug。`profiles` 表新增 `constitution_history` 列（`init_db` 自动迁移，幂等）。

**新语义**（`storage.update_profile`）：
- **过敏原**：累积合并（并集去重），**永不回退为"无"**（医学安全数据只增不减）。
- **体质**：新值有效（非"未知"/空）且不同时更新，旧值追加到 `constitution_history`；"未知"/空不覆盖。
- `ProfileWriterSkill` 提取 prompt 改为未提及留空（不再写"无"/"未知"默认值），由存储层合并。

**影响**：既有画像数据保留；过敏史不再因后续未提及过敏的轮次而丢失。
