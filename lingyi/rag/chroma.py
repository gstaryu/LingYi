"""
ChromaDB RAG 客户端 - 真实混合检索实现。

使用 ChromaDB 做持久化向量存储，支持 embedding 模型注入。
混合检索: BM25 关键词检索 + 向量检索，通过 RRF (Reciprocal Rank Fusion) 融合。
ChromaDB 原生不支持 async，用 asyncio.to_thread() / run_in_executor 包装。
"""

import asyncio
import logging
from typing import Any

from lingyi.rag.base import BaseRAGClient, RAGResult

logger = logging.getLogger(__name__)

# RRF 平滑参数 k（标准值 60）
_RRF_K = 60


class ChromaRAGClient(BaseRAGClient):
    """
    ChromaDB RAG 客户端 - BM25 + 向量混合检索。

    通过构造函数注入 embedding 模型，支持 mock/real 切换。
    混合检索流程:
    1. 向量检索: 用 embedding 模型嵌入查询，ChromaDB cosine 检索
    2. BM25 检索: 对集合中的文档做字符级 BM25 关键词检索
    3. RRF 融合: 对两路排名做 Reciprocal Rank Fusion (k=60)

    无 embedding 模型时回退到 BM25-only。
    使用 asyncio.run_in_executor() 包装同步的 ChromaDB/BM25 调用。

    多查询扩展 (multi-query) 已评估: 客户端无 LLM，非 LLM 变体（如字符 bigram 扩展）
    收益有限且增加复杂度，故推迟到 skill 层（RAGRewriteSkill 已用 LLM 做查询重写）。
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

        # BM25 索引缓存（懒加载，add_documents 后失效）
        self._bm25_index = None
        self._bm25_corpus: list[dict[str, Any]] = []  # 平行于 BM25 索引的文档信息

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

    # ------------------------------------------------------------------
    # BM25 索引管理
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """
        字符级分词 - 适用于中文古籍文本。

        将文本拆分为单个字符（过滤空白），不依赖 jieba。
        对于 TCM 古籍（文言文）效果良好: 每个汉字本身承载独立语义。
        """
        return [ch for ch in text if ch.strip()]

    def _ensure_bm25_index(self):
        """
        延迟构建 BM25 索引。

        从 ChromaDB collection.get() 拉取全部文档，按字符分词后构建 BM25Okapi。
        索引缓存在 self._bm25_index，add_documents 后置 None 触发重建。
        空集合时索引保持 None。
        """
        if self._bm25_index is not None:
            return

        from rank_bm25 import BM25Okapi

        try:
            all_data = self._collection.get()
        except Exception as e:
            logger.error("BM25 索引构建失败（无法读取集合）: %s", e)
            self._bm25_index = None
            self._bm25_corpus = []
            return

        ids = all_data.get("ids", [])
        documents = all_data.get("documents", [])
        metadatas = all_data.get("metadatas", [])

        if not documents:
            self._bm25_index = None
            self._bm25_corpus = []
            return

        # 构建分词语料
        tokenized_corpus = [self._tokenize(doc) for doc in documents]
        self._bm25_corpus = [
            {"id": _id, "content": doc, "metadata": meta or {}}
            for _id, doc, meta in zip(ids, documents, metadatas)
        ]
        self._bm25_index = BM25Okapi(tokenized_corpus)
        logger.info("BM25 索引构建完成: %d 条文档", len(self._bm25_corpus))

    def _bm25_search(
        self, query: str, n_results: int
    ) -> list[tuple[str, dict[str, Any], float]]:
        """
        BM25 关键词检索（同步，在线程池中运行）。

        Args:
            query: 查询文本
            n_results: 返回结果数量

        Returns:
            [(content, metadata, normalized_score), ...] 按相关性降序，
            仅返回 BM25 分数 > 0 的文档（无关键词匹配的文档不计入排名）。
        """
        self._ensure_bm25_index()
        if self._bm25_index is None or not self._bm25_corpus:
            return []

        tokenized_query = self._tokenize(query)
        if not tokenized_query:
            return []

        scores = self._bm25_index.get_scores(tokenized_query)

        # 按 BM25 分数降序排列
        ranked_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )

        # 仅保留分数 > 0 的结果，取 top n_results
        max_score = float(max(scores)) if len(scores) > 0 else 0.0
        results: list[tuple[str, dict[str, Any], float]] = []
        for idx in ranked_indices:
            if scores[idx] <= 0:
                break
            entry = self._bm25_corpus[idx]
            # 归一化到 0-1
            norm_score = float(scores[idx]) / max_score if max_score > 0 else 0.0
            results.append((entry["content"], entry["metadata"], norm_score))
            if len(results) >= n_results:
                break

        return results

    # ------------------------------------------------------------------
    # 向量检索
    # ------------------------------------------------------------------

    def _query_chroma(
        self,
        query: str,
        query_embedding: list[float] | None,
        n_results: int,
    ) -> list[RAGResult]:
        """同步执行 ChromaDB 向量查询（在线程池中运行），返回 RAGResult 列表。"""
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

    # ------------------------------------------------------------------
    # RRF 融合
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf_fuse(
        vector_results: list[RAGResult],
        bm25_results: list[tuple[str, dict[str, Any], float]],
        n_results: int,
        k: int = _RRF_K,
    ) -> list[RAGResult]:
        """
        Reciprocal Rank Fusion - 融合向量与 BM25 排名。

        rrf_score(d) = sum( 1 / (k + rank_i(d)) )  对每个排名系统 i
        rank 从 1 开始计数（rank=1 为最相关）。

        分数归一化: 除以理论最大值 num_rankings/(k+1)，
        使得在所有系统中均排第一的文档分数为 1.0。

        Args:
            vector_results: 向量检索结果（RAGResult 列表，已按分数降序）
            bm25_results: BM25 检索结果 [(content, metadata, score), ...]
            n_results: 返回数量
            k: RRF 平滑参数（默认 60）

        Returns:
            融合后的 RAGResult 列表，按 RRF 分数降序
        """
        # 用 content 作为文档去重键
        rrf_scores: dict[str, float] = {}
        meta_map: dict[str, tuple[str, dict[str, Any]]] = {}  # content -> (source, metadata)

        # 向量排名
        for rank, result in enumerate(vector_results, start=1):
            rrf_scores[result.content] = rrf_scores.get(result.content, 0.0) + 1.0 / (k + rank)
            if result.content not in meta_map:
                meta_map[result.content] = (result.source, result.metadata)

        # BM25 排名
        for rank, (content, metadata, _score) in enumerate(bm25_results, start=1):
            rrf_scores[content] = rrf_scores.get(content, 0.0) + 1.0 / (k + rank)
            if content not in meta_map:
                meta_map[content] = (metadata.get("book", ""), metadata)

        # 按 RRF 分数降序排列
        sorted_contents = sorted(rrf_scores.keys(), key=lambda c: rrf_scores[c], reverse=True)

        # 归一化: 理论最大值 = 2/(k+1)（两个系统均排第一）
        max_possible = 2.0 / (k + 1)

        fused: list[RAGResult] = []
        for content in sorted_contents[:n_results]:
            source, metadata = meta_map[content]
            normalized_score = rrf_scores[content] / max_possible
            fused.append(
                RAGResult(
                    content=content,
                    source=source,
                    score=normalized_score,
                    metadata=metadata,
                )
            )

        return fused

    # ------------------------------------------------------------------
    # 公开检索接口
    # ------------------------------------------------------------------

    def _hybrid_search_sync(
        self,
        query: str,
        query_embedding: list[float] | None,
        n_results: int,
    ) -> list[RAGResult]:
        """
        同步混合检索（在线程池中运行）。

        1. 向量检索: top (n_results*3) 候选
        2. BM25 检索: top (n_results*3) 候选（仅分数>0）
        3. RRF 融合两路排名
        4. 返回 top n_results

        无 embedding 时仅用 BM25。
        """
        candidate_k = max(n_results * 3, n_results)

        # --- BM25 检索 ---
        bm25_results = self._bm25_search(query, candidate_k)
        # [(content, metadata, score), ...]

        # --- 无 embedding 模型: BM25-only ---
        if query_embedding is None:
            results = [
                RAGResult(
                    content=content,
                    source=metadata.get("book", ""),
                    score=score,
                    metadata=metadata,
                )
                for content, metadata, score in bm25_results[:n_results]
            ]
            return results

        # --- 向量检索 ---
        vector_results = self._query_chroma(query, query_embedding, candidate_k)

        if not vector_results and not bm25_results:
            return []

        # 如果某一路为空，直接返回另一路
        if not bm25_results:
            return vector_results[:n_results]
        if not vector_results:
            return [
                RAGResult(
                    content=content,
                    source=metadata.get("book", ""),
                    score=score,
                    metadata=metadata,
                )
                for content, metadata, score in bm25_results[:n_results]
            ]

        # --- RRF 融合 ---
        return self._rrf_fuse(vector_results, bm25_results, n_results)

    async def search(self, query: str, top_k: int = 3) -> list[RAGResult]:
        """执行混合检索（语义等同 hybrid_search，仅截取 top_k）。"""
        return await self.hybrid_search(query, n_results=top_k)

    async def hybrid_search(self, query: str, n_results: int = 10) -> list[RAGResult]:
        """
        执行混合检索（BM25 关键词 + 向量检索，RRF 融合）。

        流程:
        1. 向量检索: 用 embedding 模型嵌入查询，ChromaDB cosine 检索，取 top (n_results*3) 候选
        2. BM25 检索: 对集合文档做字符级 BM25 关键词检索，取 top (n_results*3) 候选
        3. RRF 融合: 对两路排名做 Reciprocal Rank Fusion (k=60)，返回 top n_results

        无 embedding 模型时回退到 BM25-only。

        Args:
            query: 查询文本
            n_results: 返回结果数量

        Returns:
            RAGResult 列表（按融合后相关性降序），score 为归一化 RRF 分数 [0,1]
        """
        self._ensure_client()

        # 获取查询向量
        if self._embedding_model:
            query_embedding = await self._embedding_model.aembed_query(query)
        else:
            query_embedding = None

        # 在线程池中执行同步的混合检索
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._hybrid_search_sync(query, query_embedding, n_results),
        )

        return results

    # ------------------------------------------------------------------
    # 文档入库
    # ------------------------------------------------------------------

    async def existing_ids(self) -> set[str]:
        """
        返回集合中已存在的全部文档 ID（md5(content)）。

        供 ingest 断点续传使用：入库前先取现有 ID 集合，跳过已嵌入的文档，
        避免中断后重复嵌入（本地 CPU embedding 代价高）。
        """
        import asyncio as _asyncio

        self._ensure_client()
        loop = _asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: self._collection.get(include=[])
        )
        return set(result.get("ids", []))

    async def add_documents(self, documents: list[dict[str, Any]]) -> int:
        """
        添加文档到 ChromaDB。

        若注入了 embedding_model，则用其生成向量并显式传入 ChromaDB，
        确保入库与查询使用同一嵌入空间（否则 ChromaDB 会用其默认 MiniLM 嵌入，
        与查询时的 embedding_model 空间不一致，导致检索失效）。

        添加后使 BM25 索引缓存失效，下次检索时懒重建。
        """
        self._ensure_client()

        if not documents:
            return 0

        contents = [doc.get("content", "") for doc in documents]

        # 用注入的 embedding 模型生成向量（与查询侧一致）；无模型时回退 ChromaDB 默认嵌入
        embeddings: list[list[float]] | None = None
        if self._embedding_model:
            embeddings = await self._embedding_model.aembed_documents(contents)
        else:
            logger.warning("未注入 embedding 模型，回退 ChromaDB 默认嵌入（与查询嵌入空间可能不一致）")

        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(
            None,
            lambda: self._batch_add(documents, embeddings),
        )

        # 使 BM25 索引失效，下次检索时懒重建
        if count > 0:
            self._bm25_index = None
            self._bm25_corpus = []

        logger.info("ChromaDB 添加 %d 条文档", count)
        return count

    def _batch_add(
        self,
        documents: list[dict[str, Any]],
        embeddings: list[list[float]] | None = None,
    ) -> int:
        """批量添加文档（在线程池中运行）。embeddings 由外部异步生成后传入。"""
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
            kwargs: dict[str, Any] = {
                "ids": ids,
                "documents": contents,
                "metadatas": metadatas,
            }
            if embeddings is not None:
                kwargs["embeddings"] = embeddings
            self._collection.upsert(**kwargs)
            return len(documents)
        except Exception as e:
            logger.error("ChromaDB 批量添加失败: %s", e)
            return 0
