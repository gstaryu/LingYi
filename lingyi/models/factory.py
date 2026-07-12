"""
模型工厂 — 根据配置创建 LLM / Embedding / Reranker 实例。

设计原则:
- 工厂函数根据 Settings 返回对应的实现类实例
- 支持 mock 模式（返回 stub）用于测试
- 不在模块级创建实例，由调用方决定生命周期
"""

import logging
from typing import TYPE_CHECKING

from lingyi.models.base import BaseEmbedding, BaseLLM, BaseReranker

if TYPE_CHECKING:
    from lingyi.config import Settings

logger = logging.getLogger(__name__)


class _StubLLM(BaseLLM):
    """Stub LLM — 测试用，返回固定响应。"""

    def __init__(self, response: str = "这是一个 stub 响应，用于测试。"):
        self._response = response

    async def ainvoke(self, messages, temperature=0.7, max_tokens=2048) -> str:
        return self._response


class _StubEmbedding(BaseEmbedding):
    """Stub Embedding — 测试用，返回随机向量。"""

    def __init__(self, dim: int = 1024):
        self._dim = dim

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        import random

        random.seed(42)
        return [[random.random() for _ in range(self._dim)] for _ in texts]

    async def aembed_query(self, text: str) -> list[float]:
        import random

        random.seed(42)
        return [random.random() for _ in range(self._dim)]


class _StubReranker(BaseReranker):
    """Stub Reranker — 测试用，返回原始顺序。"""

    async def arerank(self, query, documents, top_k=5):
        return documents[:top_k]


def create_llm(settings: "Settings") -> BaseLLM:
    """
    根据配置创建 LLM 实例。

    Args:
        settings: 全局配置对象

    Returns:
        BaseLLM 实例（DashScopeLLM 或 StubLLM）
    """
    # 测试模式返回 stub
    if settings.environment == "testing":
        logger.info("使用 StubLLM（testing 环境）")
        return _StubLLM()

    from lingyi.models.dashscope import DashScopeLLM

    return DashScopeLLM(
        api_key=settings.effective_api_key,
        base_url=settings.openai_base_url,
        model_name=settings.model_name,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


def create_embeddings(settings: "Settings") -> BaseEmbedding:
    """
    根据配置创建 Embedding 实例。

    支持两种模式:
    - local: 本地 HuggingFace BGE-M3（GPU/CPU）
    - online: DashScope Embedding API

    Args:
        settings: 全局配置对象

    Returns:
        BaseEmbedding 实例
    """
    # 测试模式返回 stub
    if settings.environment == "testing":
        logger.info("使用 StubEmbedding（testing 环境）")
        return _StubEmbedding()

    if settings.embedding_mode == "local":
        from lingyi.models.local import LocalEmbedding

        return LocalEmbedding(
            model_name=settings.embedding_model_name,
            device=settings.embedding_device,
            hf_endpoint=settings.hf_endpoint,
        )
    else:
        from lingyi.models.dashscope import DashScopeEmbedding

        return DashScopeEmbedding(
            api_key=settings.effective_api_key,
            base_url=settings.openai_base_url,
            model_name=settings.embedding_model_name,
        )


def create_reranker(settings: "Settings") -> BaseReranker:
    """
    根据配置创建 Reranker 实例。

    Args:
        settings: 全局配置对象

    Returns:
        BaseReranker 实例
    """
    if settings.environment == "testing":
        logger.info("使用 StubReranker（testing 环境）")
        return _StubReranker()

    # 生产环境使用 CrossEncoder
    # 延迟导入，避免在 testing 模式下加载 sentence-transformers
    return _CrossEncoderReranker(model_name=settings.rerank_model_name)


class _CrossEncoderReranker(BaseReranker):
    """Cross-Encoder 重排器 — 使用 sentence-transformers 的 CrossEncoder。"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self._model_name = model_name
        self._model = None

    def _ensure_model(self):
        """延迟加载 CrossEncoder 模型。"""
        if self._model is not None:
            return

        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self._model_name)
        logger.info("CrossEncoder 加载完成: %s", self._model_name)

    async def arerank(self, query, documents, top_k=5):
        """异步重排文档。"""
        import asyncio

        self._ensure_model()

        if not documents:
            return []

        # 构造 query-doc 对
        pairs = [(query, doc.content) for doc in documents]

        # 异步执行重排
        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(
            None, self._model.predict, pairs
        )

        # 将分数赋值给文档并排序
        for doc, score in zip(documents, scores):
            doc.score = float(score)

        ranked = sorted(documents, key=lambda d: d.score, reverse=True)
        return ranked[:top_k]
