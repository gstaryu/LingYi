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


def create_chat_model(
    settings: "Settings", role: str = "default", max_retries: int | None = None
) -> "ChatOpenAI":
    """
    根据配置创建 ChatOpenAI 实例（支持 bind_tools / 单次 ainvoke）。

    与 create_llm 返回的 DashScopeLLM 不同，此函数返回原生 ChatOpenAI，
    因为多智能体专家需要 bind_tools 和单次 ainvoke 支持，
    而 DashScopeLLM 仅暴露 ainvoke()->str 和 with_structured_output。

    按角色读取独立模型配置；留空时回退到 settings.model_name。
    重试次数: 专家角色（bianzheng/fangji/bencao/synthesis/reviewer）默认用
    llm_specialist_max_retries（默认 1），避免网关抖动时静默 3x 重试风暴；
    其他角色用 llm_max_retries。可通过 max_retries 显式覆盖。

    Args:
        settings: 全局配置对象
        role: 角色名 - "default" / "bianzheng" / "fangji" / "bencao" / "synthesis"
            / "reviewer"，对应 settings.model_name_<role> 字段
        max_retries: 显式重试次数；None 时按角色自动选择

    Returns:
        ChatOpenAI 实例
    """
    from langchain_openai import ChatOpenAI

    # 按角色选择模型名；留空回退到默认 model_name
    role_model_map = {
        "bianzheng": settings.model_name_bianzheng,
        "fangji": settings.model_name_fangji,
        "bencao": settings.model_name_bencao,
    }
    model_name = role_model_map.get(role, "") or settings.model_name

    # 按角色选择重试次数：专家角色用更低的重试上限
    if max_retries is None:
        specialist_roles = {"bianzheng", "fangji", "bencao", "synthesis", "reviewer"}
        if role in specialist_roles:
            max_retries = settings.llm_specialist_max_retries
        else:
            max_retries = settings.llm_max_retries

    return ChatOpenAI(
        api_key=settings.effective_api_key,
        base_url=settings.openai_base_url,
        model=model_name,
        temperature=settings.llm_temperature,
        max_tokens=8192,
        timeout=settings.llm_timeout,
        max_retries=max_retries,
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
