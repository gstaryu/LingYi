# RAG 子系统

## 概述

灵医的 RAG（Retrieval-Augmented Generation）子系统负责从中医经典古籍中检索与患者症状相关的文献条文，供辨证和处方节点参考。通过 `RAG_MODE` 环境变量切换两种运行模式：

| 模式 | 配置值 | 说明 | 适用场景 |
|---|---|---|---|
| Mock | `mock`（默认） | 从本地 JSON 文件加载预设检索结果 | 本地开发、测试 |
| ChromaDB | `chroma` | ChromaDB + Embedding 向量检索 + BM25 混合检索 | 生产环境 |

## Mock 模式

`lingyi/rag/mock.py: MockRAGClient` 从 `storage/mock_rag_data.json` 加载预设检索结果。

- 无外部依赖（无需 ChromaDB、Embedding 模型）
- 支持按查询模式匹配返回不同结果
- 有默认结果兜底
- 生成方式：`python -m data_pipeline.ingest --mode mock`

## ChromaDB 模式

`lingyi/rag/chroma.py: ChromaRAGClient` 使用 ChromaDB 持久化向量存储，支持混合检索。

### 混合检索

`hybrid_search(query, n_results)` 方法执行三步流程：

1. **向量检索**：用 Embedding 模型嵌入查询，ChromaDB cosine 检索，取 top `(n_results*3)` 候选
2. **BM25 检索**：对集合文档做字符级 BM25 关键词检索，取 top `(n_results*3)` 候选（仅分数 > 0 的文档）
3. **RRF 融合**：对两路排名做 Reciprocal Rank Fusion（k=60），返回 top `n_results`

#### BM25 索引

- **字符级分词**：将文本拆分为单个字符（过滤空白），不依赖 jieba，适用于中医古籍文言文
- **懒加载**：首次检索时从 ChromaDB `collection.get()` 拉取全部文档构建 `BM25Okapi` 索引
- **失效重建**：`add_documents` 后将索引置 None，下次检索时懒重建
- **无 embedding 时回退**：仅用 BM25 检索

#### RRF 融合算法

```
rrf_score(d) = sum( 1 / (k + rank_i(d)) )  对每个排名系统 i
```

- `rank` 从 1 开始计数（rank=1 为最相关）
- `k = 60`（标准平滑参数）
- 分数归一化：除以理论最大值 `2/(k+1)`（两个系统均排第一时为 1.0）
- 用 `content` 作为文档去重键

### 异步包装

ChromaDB 原生不支持 async，使用 `asyncio.get_running_loop().run_in_executor()` 包装同步调用。

## Embedding 模型

通过 `EMBEDDING_MODE` 环境变量切换：

| 模式 | 配置值 | 模型 | 说明 |
|---|---|---|---|
| 本地 | `local`（默认） | HuggingFace Qwen3-Embedding-0.6B | 1024 维，instruction-aware |
| 在线 | `online` | DashScope text-embedding-v4 | API 调用，无需本地 GPU |

### 本地模式

- 模型：`Qwen/Qwen3-Embedding-0.6B`（`EMBEDDING_MODEL_NAME` 可配置）
- 设备：`cuda`（默认）/ `cpu`（`EMBEDDING_DEVICE` 可配置）
- 查询嵌入使用 `query_prompt_name`（`EMBEDDING_QUERY_PROMPT_NAME`，Qwen3-Embedding 需设为 `"query"`，留空则按模型名自动检测）
- HuggingFace 镜像：`HF_ENDPOINT` 环境变量（默认 `https://hf-mirror.com`，镜像不可达时设为 `https://huggingface.co`）

### 在线模式

- 模型：`text-embedding-v4`（`EMBEDDING_ONLINE_MODEL_NAME` 可配置）
- 通过 DashScope API 调用

### 入库与查询一致性

`ChromaRAGClient.add_documents()` 使用注入的 embedding 模型生成向量并显式传入 ChromaDB，确保入库与查询使用同一嵌入空间。

## 重排器

`lingyi/rag/reranker.py` 提供可选的 Cross-Encoder 精排：

| 模式 | 重排器 | 模型 |
|---|---|---|
| Mock | `MockReranker` | 透传结果 |
| Chroma | `CrossEncoderReranker` | `BAAI/bge-reranker-v2-m3`（`RERANK_MODEL_NAME` 可配置） |

### 检索流程

`RAGSearchSkill`（`lingyi/agent/skills/rag_search.py`）执行检索：

1. **粗排**：`hybrid_search(query, n_results=recall_k)` 召回 `rag_recall_k`（默认 15）条
2. **精排**：Cross-Encoder 重排，取 top `rag_rerank_k`（默认 5）条
3. 无 reranker 时跳过精排，向后兼容

### 配置项

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `RAG_RECALL_K` | 15 | 粗排召回 Top-K |
| `RAG_RERANK_K` | 5 | 精排截取 Top-K |
| `RAG_SCORE_THRESHOLD` | 0.7 | RAG 质量及格分数线 |
| `RAG_MAX_RETRIES` | 3 | RAG 搜索最大重试次数 |
| `RAG_ENABLE_EVALUATION` | false | 是否启用 RAG 质量评估循环 |

## RAG 质量评估

`RAGGraderSkill` 使用 `with_structured_output(RAGGradeResult)` 评估检索质量：

| 字段 | 类型 | 说明 |
|---|---|---|
| `score` | `float` | 相关性评分 0.0-1.0 |
| `reasoning` | `str` | 评分理由 |

评分标准：0.8+ 直接相关，0.6-0.8 部分相关，0.6 以下关联较弱。

### 评估环路

`RAG_ENABLE_EVALUATION=true` 时启用评估-重写循环：

```
rag_search -> rag_grader -> (score >= 0.7 或重试耗尽 -> diagnosis | 否则 -> rag_rewrite -> rag_search)
```

`RAGRewriteSkill` 将口语化症状转化为专业中医术语，用于二次检索。

默认关闭（`false`），启用后会增加 LLM 调用次数。

## 数据入库

### ChromaDB 入库

```bash
python -m data_pipeline.ingest --mode chroma
```

- 异步入库（`asyncio.run(ingest_to_chroma)`）
- 分批处理，每批 64 条（`BATCH_SIZE = 64`）
- 使用 `settings` 中的 embedding 配置创建嵌入模型与 ChromaRAGClient
- 文档 ID 用 content 的 MD5 哈希（幂等 upsert）

### Mock 数据生成

```bash
python -m data_pipeline.ingest --mode mock
```

从切分结果中采样生成 `storage/mock_rag_data.json`，包含预设查询和默认结果。

### 数据源

古籍文本位于 `TCM_data/` 目录，包含：

| 古籍 | 文件名 |
|---|---|
| 伤寒论 | 伤寒论_完整清洗版.txt |
| 金匮要略 | 金匮要略_完整清洗版.txt |
| 温病条辨 | 温病条辨_完整清洗版.txt |
| 神农本草经 | 神农本草经_完整清洗版.txt |
| 脉经 | 脉经_完整清洗版.txt |
| 黄帝内经-素问 | 黄帝内经-素问_完整清洗版.txt |

## RAG 路由逻辑

`rag_decision_logic(state)` 判断是否需要启动知识检索：

| 条件 | 路由 |
|---|---|
| 非就诊意图（chat 等） | `end` |
| diagnose 意图且有症状 | `rag_search` |
| 其他 | `diagnosis`（跳过检索） |

`rag_loop_logic(state, score_threshold, max_retries)` 判断是否需要重写查询重试：

| 条件 | 路由 |
|---|---|
| `score >= score_threshold` 或重试耗尽 | `diagnose` |
| 否则 | `rag_rewrite` |
