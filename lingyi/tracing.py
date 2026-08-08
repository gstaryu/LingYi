"""
LangSmith 链路追踪配置。

LangGraph / LangChain 通过环境变量自动接入 LangSmith 追踪，无需代码侵入。
本模块在应用启动时按配置设置这些环境变量。
"""

import logging
import os

logger = logging.getLogger(__name__)


def setup_tracing(settings) -> None:
    """
    根据配置启用 LangSmith 追踪。

    设置 LANGSMITH_* 环境变量后，LangChain/LangGraph 会自动上报 trace，
    便于调试 agentic 推理链路（尤其在多智能体场景下定位节点行为）。

    Args:
        settings: Settings 实例
    """
    if not settings.enable_tracing:
        return
    if not settings.langsmith_api_key:
        logger.warning("enable_tracing=True 但未配置 langsmith_api_key，跳过追踪")
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project or "lingyi"
    logger.info("LangSmith 追踪已启用: project=%s", settings.langsmith_project)
