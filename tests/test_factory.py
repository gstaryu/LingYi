"""
模型工厂测试 - 验证 create_llm / create_embeddings 根据配置返回正确的实现类型。

构造函数不触发真实 API/模型加载（LocalEmbedding/DashScopeEmbedding 均为懒加载），
因此无需真实密钥即可测试工厂路由逻辑。
"""

import pytest

from lingyi.config import Settings
from lingyi.models.base import BaseEmbedding, BaseLLM


def _settings(**overrides) -> Settings:
    """构造带占位密钥的测试 Settings，避免空 key 触发校验错误。"""
    base = {
        "_env_file": None,
        "openai_api_key": "sk-test",
        "openai_base_url": "http://localhost/v1",
    }
    base.update(overrides)
    return Settings(**base)


class TestFactory:
    """模型工厂测试套件。"""

    def test_create_llm_returns_dashscope(self):
        """create_llm 应返回 DashScopeLLM 实例。"""
        from lingyi.models.dashscope import DashScopeLLM
        from lingyi.models.factory import create_llm

        llm = create_llm(_settings(model_name="qwen-max"))
        assert isinstance(llm, BaseLLM)
        assert isinstance(llm, DashScopeLLM)

    def test_create_embeddings_online(self):
        """embedding_mode=online 应返回 DashScopeEmbedding。"""
        from lingyi.models.dashscope import DashScopeEmbedding
        from lingyi.models.factory import create_embeddings

        emb = create_embeddings(_settings(embedding_mode="online"))
        assert isinstance(emb, BaseEmbedding)
        assert isinstance(emb, DashScopeEmbedding)

    def test_create_embeddings_local(self):
        """embedding_mode=local 应返回 LocalEmbedding（懒加载，不触发模型下载）。"""
        from lingyi.models.local import LocalEmbedding
        from lingyi.models.factory import create_embeddings

        emb = create_embeddings(_settings(embedding_mode="local"))
        assert isinstance(emb, BaseEmbedding)
        assert isinstance(emb, LocalEmbedding)
