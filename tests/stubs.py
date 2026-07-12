"""
测试桩（Stubs）- 用于单元测试的可控模型实现。

设计原则:
- 测试基础设施与生产代码分离（不放在 lingyi.models.factory 中）
- 桩对象实现生产抽象基类，可被任意需要 BaseLLM/BaseEmbedding/BaseReranker 的代码注入
- 响应可控、零外部依赖，保证测试快速且可离线运行
"""

from lingyi.models.base import BaseEmbedding, BaseLLM
from lingyi.rag.base import BaseReranker, RAGResult


class StubLLM(BaseLLM):
    """桩 LLM - 返回预设响应，用于测试不依赖真实 API 的 Skill/Graph 流程。"""

    def __init__(self, response: str = "这是一个 stub 响应，用于测试。", structured=None):
        """
        Args:
            response: ainvoke 返回的字符串
            structured: with_structured_output 的 ainvoke 返回的对象（如 InquiryResult 实例）
        """
        self._response = response
        self._structured = structured

    async def ainvoke(
        self, messages: list, temperature: float = 0.7, max_tokens: int = 2048
    ) -> str:
        return self._response

    def with_structured_output(self, schema):
        """返回桩 Runnable，ainvoke 返回构造时传入的 structured 对象。"""
        structured = self._structured

        class _StubStructured:
            async def ainvoke(self_inner, messages, **kwargs):
                return structured

        return _StubStructured()


class StubEmbedding(BaseEmbedding):
    """桩 Embedding - 返回固定种子的伪随机向量，保证向量维度一致且可复现。"""

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


class StubReranker(BaseReranker):
    """桩 Reranker - 原样返回前 top_k 个文档，不改变顺序。"""

    async def rerank(
        self, query: str, documents: list[RAGResult], top_k: int = 5
    ) -> list[RAGResult]:
        return documents[:top_k]
