"""
模型抽象层 — LLM / Embedding / Reranker 的抽象基类。

设计原则:
- 所有模型操作均为异步（async/await）
- 通过构造函数注入配置，不依赖全局单例
- 子类只需实现对应的抽象方法
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """检索文档 — RAG 检索返回的文档片段。"""

    content: str
    """文档正文内容。"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """元数据（来源、章节、页码等）。"""

    score: float = 0.0
    """相关性得分（0-1）。"""


class BaseLLM(ABC):
    """
    大语言模型抽象基类。

    所有 LLM 实现（DashScope、本地 vLLM 等）都继承此类。
    接受 LangChain BaseMessage 对象或 dict 格式的消息。
    """

    @abstractmethod
    async def ainvoke(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        异步调用 LLM。

        Args:
            messages: 消息列表，支持两种格式:
                - LangChain BaseMessage 对象列表 (推荐)
                - dict 格式 [{"role": "system"|"user"|"assistant", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            LLM 生成的文本内容
        """

    def invoke(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """同步调用 LLM（默认实现，子类可覆盖以提供更优的同步策略）。"""
        import asyncio

        return asyncio.run(self.ainvoke(messages, temperature, max_tokens))


class BaseEmbedding(ABC):
    """
    文本嵌入模型抽象基类。

    支持两种模式:
    - local: 本地 HuggingFace 模型（如 BGE-M3）
    - online: 第三方 API（如 DashScope Embedding API）
    """

    @abstractmethod
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """
        异步批量嵌入文档。

        Args:
            texts: 待嵌入的文本列表

        Returns:
            嵌入向量列表，与输入 texts 一一对应
        """

    @abstractmethod
    async def aembed_query(self, text: str) -> list[float]:
        """
        异步嵌入查询文本。

        Args:
            text: 查询文本

        Returns:
            嵌入向量
        """


class BaseReranker(ABC):
    """
    重排模型抽象基类。

    对 RAG 检索到的文档进行重新排序，提升相关文档的排名。
    """

    @abstractmethod
    async def arerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int = 5,
    ) -> list[Document]:
        """
        异步重排文档。

        Args:
            query: 查询文本
            documents: 待重排的文档列表
            top_k: 返回前 K 个文档

        Returns:
            重排后的文档列表（按相关性降序）
        """
