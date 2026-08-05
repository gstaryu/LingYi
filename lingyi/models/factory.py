"""
模型工厂 - 根据配置创建 LLM / Embedding 实例。

设计原则:
- 工厂函数根据 Settings 返回对应的实现类实例
- 不在模块级创建实例，由调用方决定生命周期
- 测试桩（StubLLM/StubEmbedding）定义在 tests/stubs.py，由测试直接注入，
  生产工厂不感知"测试环境"，避免 env 驱动的依赖注入分支。

注: RAG 重排器的构造属于 RAG 领域，见 lingyi/rag/reranker.py。
"""

import logging
from typing import TYPE_CHECKING

from lingyi.models.base import BaseEmbedding, BaseLLM

if TYPE_CHECKING:
    from lingyi.config import Settings

logger = logging.getLogger(__name__)


def create_llm(settings: "Settings") -> BaseLLM:
    """
    根据配置创建 LLM 实例。

    Args:
        settings: 全局配置对象

    Returns:
        BaseLLM 实例（DashScopeLLM）
    """
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
    - local: 本地 HuggingFace 模型（默认 Qwen3-Embedding-0.6B，instruction-aware）
    - online: DashScope Embedding API（text-embedding-v4）

    Args:
        settings: 全局配置对象

    Returns:
        BaseEmbedding 实例
    """
    if settings.embedding_mode == "local":
        from lingyi.models.local import LocalEmbedding

        # 查询 prompt：优先用显式配置；否则按模型名自动检测（Qwen3-Embedding 需 "query"）
        query_prompt = settings.embedding_query_prompt_name
        if not query_prompt and "qwen3-embedding" in settings.embedding_model_name.lower():
            query_prompt = "query"

        return LocalEmbedding(
            model_name=settings.embedding_model_name,
            device=settings.embedding_device,
            hf_endpoint=settings.hf_endpoint,
            query_prompt_name=query_prompt or None,
        )

    from lingyi.models.dashscope import DashScopeEmbedding

    # online 模式用 DashScope 的 text-embedding-v4（与本地 Qwen3 模型名解耦）
    return DashScopeEmbedding(
        api_key=settings.effective_api_key,
        base_url=settings.openai_base_url,
        model_name=settings.embedding_online_model_name,
    )
