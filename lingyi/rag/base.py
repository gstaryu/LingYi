"""
RAG 抽象基类 — 定义统一的检索接口。

支持两种实现:
- MockRAGClient: 从文件加载预设结果，用于开发和测试
- ChromaRAGClient: 真实向量检索，用于生产环境
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RAGResult:
    """RAG 检索结果。"""

    content: str
    """文档正文内容。"""

    source: str = ""
    """来源（书名、章节等）。"""

    score: float = 0.0
    """相关性得分（0-1）。"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """其他元数据。"""


class BaseRAGClient(ABC):
    """
    RAG 检索客户端抽象基类。

    所有 RAG 实现（Mock、ChromaDB 等）都继承此类。
    """

    @abstractmethod
    async def search(self, query: str, top_k: int = 3) -> list[RAGResult]:
        """
        简单向量检索。

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            RAGResult 列表（按相关性降序）
        """

    @abstractmethod
    async def hybrid_search(self, query: str, n_results: int = 10) -> list[dict[str, Any]]:
        """
        混合检索（向量 + 关键词）。

        Args:
            query: 查询文本
            n_results: 返回结果数量

        Returns:
            [{"content": "...", "source": "...", "score": 0.9, "metadata": {...}}]
        """

    async def add_documents(self, documents: list[dict[str, Any]]) -> int:
        """
        添加文档到向量库（可选实现）。

        Args:
            documents: [{"content": "...", "metadata": {...}}]

        Returns:
            成功添加的文档数量
        """
        return 0
