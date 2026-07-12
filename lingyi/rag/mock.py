"""
Mock RAG 客户端 — 从 JSON 文件加载预设检索结果。

用于本地开发和测试，不需要 GPU 或 embedding 模型。
支持两种模式:
1. 从 JSON 文件加载预设结果（按 query pattern 匹配）
2. 手动传入文档列表
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from lingyi.rag.base import BaseRAGClient, RAGResult

logger = logging.getLogger(__name__)


class MockRAGClient(BaseRAGClient):
    """
    Mock RAG 客户端。

    从 JSON 文件加载预设的检索结果，按 query pattern 正则匹配。
    不执行真实的向量检索，适合离线开发和单元测试。
    """

    def __init__(self, data_path: str | None = None, default_results: list[dict] | None = None):
        """
        初始化 Mock RAG 客户端。

        Args:
            data_path: mock 数据 JSON 文件路径
            default_results: 默认返回结果（当无匹配时使用）
        """
        self._queries: list[dict[str, Any]] = []
        self._default_results = default_results or []

        if data_path and Path(data_path).exists():
            self._load_data(data_path)
            logger.info("MockRAGClient 加载数据: %s (%d 条规则)", data_path, len(self._queries))
        else:
            logger.info("MockRAGClient 使用默认结果")

    def _load_data(self, data_path: str) -> None:
        """从 JSON 文件加载 mock 数据。"""
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)

        self._queries = data.get("queries", [])
        if not self._default_results:
            self._default_results = data.get("default_results", [])

    async def search(self, query: str, top_k: int = 3) -> list[RAGResult]:
        """根据 query pattern 匹配预设结果。"""
        results = self._match_query(query)
        return self._to_rag_results(results)[:top_k]

    async def hybrid_search(self, query: str, n_results: int = 10) -> list[RAGResult]:
        """根据 query pattern 匹配预设结果（与 search 同语义，Mock 不区分检索策略）。"""
        results = self._match_query(query)
        return self._to_rag_results(results)[:n_results]

    def _match_query(self, query: str) -> list[dict[str, Any]]:
        """按正则匹配 query pattern，返回原始 dict 结果。"""
        for entry in self._queries:
            pattern = entry.get("query_pattern", "")
            if pattern and re.search(pattern, query):
                return entry.get("results", [])

        # 无匹配时返回默认结果
        return self._default_results

    @staticmethod
    def _to_rag_results(raw: list[dict[str, Any]]) -> list[RAGResult]:
        """将内部 dict 结果转换为 RAGResult 列表。"""
        return [
            RAGResult(
                content=r.get("content", ""),
                source=r.get("source", ""),
                score=r.get("score", 0.8),
                metadata=r.get("metadata", {}),
            )
            for r in raw
        ]

    async def add_documents(self, documents: list[dict[str, Any]]) -> int:
        """Mock 模式下直接添加到内存默认结果。"""
        self._default_results.extend(documents)
        return len(documents)
