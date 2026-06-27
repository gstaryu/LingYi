"""
RAG 重排器 — 对检索结果进行重新排序。

支持两种实现:
- MockReranker: 返回原始顺序（测试用）
- CrossEncoderReranker: 使用 Cross-Encoder 模型重排（生产用）
"""

import asyncio
import logging
from typing import Any

from lingyi.rag.base import RAGResult

logger = logging.getLogger(__name__)


class MockReranker:
    """Mock 重排器 — 返回原始顺序，用于测试。"""

    async def rerank(
        self, query: str, documents: list[RAGResult], top_k: int = 5
    ) -> list[RAGResult]:
        """直接返回前 top_k 个文档，不改变顺序。"""
        return documents[:top_k]


class CrossEncoderReranker:
    """
    Cross-Encoder 重排器。

    使用 sentence-transformers 的 CrossEncoder 模型对检索结果进行重排。
    延迟加载模型，避免启动时占用显存。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        """
        初始化 Cross-Encoder 重排器。

        Args:
            model_name: Cross-Encoder 模型名称
        """
        self._model_name = model_name
        self._model = None

    def _ensure_model(self):
        """延迟加载 CrossEncoder 模型。"""
        if self._model is not None:
            return

        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self._model_name)
        logger.info("CrossEncoder 加载完成: %s", self._model_name)

    async def rerank(
        self, query: str, documents: list[RAGResult], top_k: int = 5
    ) -> list[RAGResult]:
        """
        异步重排文档。

        Args:
            query: 查询文本
            documents: 待重排的文档列表
            top_k: 返回前 K 个文档

        Returns:
            重排后的文档列表（按相关性降序）
        """
        if not documents:
            return []

        self._ensure_model()

        # 构造 query-doc 对
        pairs = [(query, doc.content) for doc in documents]

        # 异步执行重排
        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(None, self._model.predict, pairs)

        # 将分数赋值给文档并排序
        for doc, score in zip(documents, scores):
            doc.score = float(score)

        ranked = sorted(documents, key=lambda d: d.score, reverse=True)
        return ranked[:top_k]
