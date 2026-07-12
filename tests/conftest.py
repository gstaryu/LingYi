"""
公共测试 Fixtures — mock LLM、mock RAG、临时数据库等。

所有测试共享的 fixtures 集中在此处，避免重复代码。
"""

import os
import sys
import tempfile

import pytest

# 确保项目根目录在 path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture
def mock_llm():
    """返回可控响应的 Stub LLM。"""
    from tests.stubs import StubLLM
    return StubLLM(response='{"intent_type": "chat", "symptoms": [], "response": "测试回复"}')


@pytest.fixture
def mock_llm_json():
    """返回 JSON 响应的 Stub LLM。"""

    class JsonLLM:
        def __init__(self, response: str):
            self._response = response

        async def ainvoke(self, messages, temperature=0.7, max_tokens=2048):
            return self._response

    return JsonLLM


@pytest.fixture
def mock_rag_client():
    """返回预设文档的 MockRAGClient。"""
    from lingyi.rag.mock import MockRAGClient

    return MockRAGClient(
        default_results=[
            {"content": "太阴之为病，腹满而吐，食不下，自利益甚。", "source": "伤寒论", "score": 0.9},
            {"content": "太阳之为病，脉浮，头项强痛而恶寒。", "source": "伤寒论", "score": 0.85},
        ]
    )


@pytest.fixture
def safety_engine():
    """返回 SafetyEngine 实例。"""
    from lingyi.safety.rules import SafetyEngine
    return SafetyEngine()


@pytest.fixture
def tmp_db(tmp_path):
    """返回临时 SQLite 数据库路径。"""
    return str(tmp_path / "test.db")


@pytest.fixture
def tmp_storage(tmp_db):
    """返回临时 SQLiteStorage 实例。"""
    from lingyi.storage.sqlite import SQLiteStorage
    return SQLiteStorage(tmp_db)


@pytest.fixture
def test_settings():
    """返回测试用 Settings（不依赖环境变量，不污染全局缓存）。"""
    from lingyi.config import Settings
    return Settings(_env_file=None)
