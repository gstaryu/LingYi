"""
FastAPI 依赖注入 — 创建和管理 Agent、Storage、RAG 等实例。

使用 FastAPI 的 Depends 机制，在请求级别注入依赖。
"""

import logging
from typing import Any

from lingyi.config import Settings, get_settings

logger = logging.getLogger(__name__)

# 全局缓存的实例（应用生命周期内只创建一次）
_agent_instance: Any = None
_storage_instance: Any = None
_rag_client_instance: Any = None
_safety_engine_instance: Any = None


def get_storage(settings: Settings | None = None):
    """获取存储实例。"""
    global _storage_instance
    if _storage_instance is None:
        from lingyi.storage.sqlite import SQLiteStorage
        _storage_instance = SQLiteStorage(settings.db_path if settings else get_settings().db_path)
    return _storage_instance


def get_safety_engine():
    """获取安全引擎实例。"""
    global _safety_engine_instance
    if _safety_engine_instance is None:
        from lingyi.safety.rules import SafetyEngine
        _safety_engine_instance = SafetyEngine()
    return _safety_engine_instance


def get_rag_client(settings: Settings | None = None):
    """获取 RAG 客户端实例。"""
    global _rag_client_instance
    if _rag_client_instance is not None:
        return _rag_client_instance

    s = settings or get_settings()
    if s.rag_mode == "chroma":
        from lingyi.rag.chroma import ChromaRAGClient
        from lingyi.models.factory import create_embeddings
        embeddings = create_embeddings(s)
        _rag_client_instance = ChromaRAGClient(
            chroma_db_dir=s.chroma_db_dir,
            embedding_model=embeddings,
        )
    else:
        from lingyi.rag.mock import MockRAGClient
        import os
        mock_data_path = os.path.join(s.storage_dir, "mock_rag_data.json")
        _rag_client_instance = MockRAGClient(data_path=mock_data_path)
    return _rag_client_instance


def get_agent(settings: Settings | None = None):
    """获取 Agent 实例。"""
    global _agent_instance
    if _agent_instance is not None:
        return _agent_instance

    from lingyi.models.factory import create_llm
    from lingyi.agent.graph import create_agent

    s = settings or get_settings()
    llm = create_llm(s)
    storage = get_storage(s)
    rag_client = get_rag_client(s)
    safety_engine = get_safety_engine()

    _agent_instance = create_agent(
        llm=llm,
        rag_client=rag_client,
        storage=storage,
        safety_engine=safety_engine,
        settings=s,
    )
    return _agent_instance


def reset_instances():
    """重置所有缓存实例（用于测试）。"""
    global _agent_instance, _storage_instance, _rag_client_instance, _safety_engine_instance
    _agent_instance = None
    _storage_instance = None
    _rag_client_instance = None
    _safety_engine_instance = None
