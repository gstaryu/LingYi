# RAG 子系统说明

## 概述

灵医的 RAG 子系统支持两种模式，通过 `RAG_MODE` 切换：

| 模式 | 说明 | 场景 |
|---|---|---|
| `mock` | 从 JSON 文件加载预设结果 | 本地开发、测试 |
| `chroma` | ChromaDB + BGE-M3 向量检索 | 生产环境 |

## 接口设计

```python
class BaseRAGClient(ABC):
    async def search(self, query: str, top_k: int = 3) -> list[RAGResult]: ...
    async def hybrid_search(self, query: str, n_results: int = 10) -> list[dict]: ...
```

## Embedding 模式

| 模式 | 配置 | 说明 |
|---|---|---|
| `local` | `EMBEDDING_MODE=local` | HuggingFace BGE-M3（GPU/CPU） |
| `online` | `EMBEDDING_MODE=online` | DashScope Embedding API |

## Mock 数据格式

`storage/mock_rag_data.json`：

```json
{
  "queries": [
    {
      "query_pattern": "脾胃虚寒|腹胀",
      "results": [
        {"content": "太阴之为病...", "source": "伤寒论", "score": 0.92}
      ]
    }
  ],
  "default_results": [...]
}
```

## RAG 工作流

1. **路由判断** — 是否需要检索（简单证候跳过）
2. **向量检索** — 从古籍库中召回相关条文
3. **质量评估**（可选）— LLM 评估检索结果与症状的关联度
4. **查询重写**（可选）— 若评分 < 0.7，将口语化症状转化为专业术语重试（最多 3 次）

## RAG 评估开关

通过 `RAG_ENABLE_EVALUATION` 配置是否启用质量评估循环：

| 值 | 行为 | 适用场景 |
|---|---|---|
| `false`（默认） | RAG 检索后直接进入辨证 | 快速响应，减少 LLM 调用 |
| `true` | 检索后经 grader 评估，低分时重写重试 | 检索质量要求高 |

关闭评估时，流程为：`rag_search → diagnosis`（1 次检索，0 次额外 LLM 调用）
开启评估时，流程为：`rag_search → rag_grader → (diagnosis | rag_rewrite → rag_search)`（最多 3 次重试，每次 2 次 LLM 调用）
