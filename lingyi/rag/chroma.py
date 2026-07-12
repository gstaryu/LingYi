"""
ChromaDB RAG 客户端 — 真实向量检索实现。

使用 ChromaDB 做持久化向量存储，支持 embedding 模型注入。
ChromaDB 原生不支持 async，用 asyncio.to_thread() 包装。
"""

import asyncio
import logging
from typing import Any

from lingyi.rag.base import BaseRAGClient, RAGResult

logger = logging.getLogger(__name__)


class ChromaRAGClient(BaseRAGClient):
    """
    ChromaDB RAG 客户端。

    通过构造函数注入 embedding 模型，支持 mock/real 切换。
    使用 asyncio.to_thread() 包装同步的 ChromaDB 调用。
    """

    def __init__(
        self,
        chroma_db_dir: str,
        embedding_model: Any = None,
        collection_name: str = "tcm_classics",
    ):
        """
        初始化 ChromaDB RAG 客户端。

        Args:
            chroma_db_dir: ChromaDB 持久化目录
            embedding_model: BaseEmbedding 实例（用于查询向量化）
            collection_name: 集合名称
        """
        self._chroma_db_dir = chroma_db_dir
        self._embedding_model = embedding_model
        self._collection_name = collection_name
        self._client = None
        self._collection = None

        logger.info("ChromaRAGClient 初始化: dir=%s, collection=%s", chroma_db_dir, collection_name)

    def _ensure_client(self):
        """延迟初始化 ChromaDB 客户端。"""
        if self._client is not None:
            return

        import chromadb

        self._client = chromadb.PersistentClient(path=self._chroma_db_dir)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB 连接完成: %s", self._collection_name)

    async def search(self, query: str, top_k: int = 3) -> list[RAGResult]:
        """执行向量检索（语义等同 hybrid_search，仅截取 top_k）。"""
        return await self.hybrid_search(query, n_results=top_k)

    async def hybrid_search(self, query: str, n_results: int = 10) -> list[RAGResult]:
        """
        执行检索。

        当前实现为纯向量检索（有 embedding 时）或纯文本检索（无 embedding 时）。
        真正的"向量+关键词"混合检索为后续增强项；接口名沿用 hybrid_search 以与
        BaseRAGClient 契约一致，避免破坏调用方。
        """
        self._ensure_client()

        # 获取查询向量
        if self._embedding_model:
            query_embedding = await self._embedding_model.aembed_query(query)
        else:
            query_embedding = None

        # 在线程池中执行同步的 ChromaDB 查询
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._query_chroma(query, query_embedding, n_results),
        )

        return results

    def _query_chroma(
        self,
        query: str,
        query_embedding: list[float] | None,
        n_results: int,
    ) -> list[RAGResult]:
        """同步执行 ChromaDB 查询（在线程池中运行），返回 RAGResult 列表。"""
        try:
            kwargs: dict[str, Any] = {"n_results": n_results}

            if query_embedding:
                kwargs["query_embeddings"] = [query_embedding]
            else:
                kwargs["query_texts"] = [query]

            results = self._collection.query(**kwargs)

            # 解析结果
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            parsed: list[RAGResult] = []
            for doc, meta, dist in zip(documents, metadatas, distances):
                # ChromaDB cosine 距离 = 1 - 余弦相似度，范围 [0,2]（0=相同，2=相反）
                # 转换为相关性分数 [0,1]：score = max(0, 1 - dist)（正交=0，相反=0）
                score = max(0.0, 1 - dist) if dist is not None else 0.0
                parsed.append(
                    RAGResult(
                        content=doc,
                        source=meta.get("book", "") if meta else "",
                        score=score,
                        metadata=meta or {},
                    )
                )

            return parsed

        except Exception as e:
            logger.error("ChromaDB 查询失败: %s", e)
            return []

    async def add_documents(self, documents: list[dict[str, Any]]) -> int:
        """添加文档到 ChromaDB。"""
        self._ensure_client()

        if not documents:
            return 0

        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(
            None,
            lambda: self._batch_add(documents),
        )

        logger.info("ChromaDB 添加 %d 条文档", count)
        return count

    def _batch_add(self, documents: list[dict[str, Any]]) -> int:
        """批量添加文档（在线程池中运行）。"""
        import hashlib

        ids = []
        contents = []
        metadatas = []

        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            doc_id = hashlib.md5(content.encode()).hexdigest()
            ids.append(doc_id)
            contents.append(content)
            metadatas.append(metadata)

        try:
            self._collection.upsert(
                ids=ids,
                documents=contents,
                metadatas=metadatas,
            )
            return len(documents)
        except Exception as e:
            logger.error("ChromaDB 批量添加失败: %s", e)
            return 0
