"""
RAG 检索技能测试 - 验证 RAGSearchSkill 调用 RAG client 并正确提取文档内容。

使用 MockRAGClient（返回 RAGResult），不依赖真实向量库或 embedding。
"""

import pytest

from lingyi.agent.skills.rag_search import RAGSearchSkill
from lingyi.rag.mock import MockRAGClient


class TestRAGSearchSkill:
    """RAGSearchSkill 测试套件。"""

    @pytest.fixture
    def rag_client(self) -> MockRAGClient:
        """返回带预设结果的 MockRAGClient。"""
        return MockRAGClient(
            default_results=[
                {"content": "太阴之为病，腹满而吐，食不下，自利益甚。", "source": "伤寒论", "score": 0.9},
                {"content": "太阳之为病，脉浮，头项强痛而恶寒。", "source": "伤寒论", "score": 0.85},
            ]
        )

    @pytest.mark.asyncio
    async def test_search_returns_docs(self, rag_client):
        """有症状时应检索并返回文档内容列表。"""
        skill = RAGSearchSkill(llm=None, rag_client=rag_client, recall_k=10)
        result = await skill.execute({"symptoms": ["腹满", "吐"]})
        assert len(result["retrieved_docs"]) == 2
        assert "太阴" in result["retrieved_docs"][0]

    @pytest.mark.asyncio
    async def test_search_empty_symptoms(self, rag_client):
        """无症状（空查询）时不检索，返回空列表。"""
        skill = RAGSearchSkill(llm=None, rag_client=rag_client)
        result = await skill.execute({"symptoms": []})
        assert result["retrieved_docs"] == []

    @pytest.mark.asyncio
    async def test_search_no_client(self):
        """未注入 rag_client 时安全返回空列表，不抛异常。"""
        skill = RAGSearchSkill(llm=None, rag_client=None)
        result = await skill.execute({"symptoms": ["发热"]})
        assert result["retrieved_docs"] == []
