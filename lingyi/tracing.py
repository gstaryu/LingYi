"""
Langfuse 链路追踪配置（自托管）。

接入方式：Langfuse 通过 LangChain Callback 机制工作——把 CallbackHandler 放进调用
graph 时的 config["callbacks"]，LangGraph 会把它传播到所有子 run（节点、LLM 调用、
工具调用），自动生成嵌套的 trace 树，无需侵入业务节点。

凭证通过 LANGFUSE_* 环境变量读取，因此必须在创建 CallbackHandler 之前设置好。
"""

import logging
import os

logger = logging.getLogger(__name__)


def setup_tracing(settings) -> None:
    """
    把 Langfuse 凭证写入环境变量。

    Langfuse SDK 的 client 是进程级单例，首次创建时读取这些环境变量，
    因此本函数必须在 create_langfuse_callbacks 之前调用（lifespan 中已保证顺序）。

    Args:
        settings: Settings 实例
    """
    if not settings.enable_langfuse:
        return
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("enable_langfuse=True 但未配置 langfuse_public_key/secret_key，跳过追踪")
        return

    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host
    os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = settings.environment
    logger.info(
        "Langfuse 追踪已启用: host=%s, environment=%s", settings.langfuse_host, settings.environment
    )


def create_langfuse_callbacks(settings) -> list:
    """
    创建传给 LangGraph config["callbacks"] 的回调列表。

    未启用或凭证缺失时返回空列表，调用方可据此跳过注入。

    Returns:
        [CallbackHandler()] 或 []
    """
    if not settings.enable_langfuse:
        return []
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return []

    # 懒导入：确保上面的环境变量已就绪后再初始化 SDK
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler()]


def trace_metadata(
    *,
    thread_id: str,
    username: str,
    member_id: str | None = None,
    agent_mode: str = "workflow",
    streaming: bool = False,
) -> dict:
    """
    构造 Langfuse 可识别的 trace 元数据。

    Langfuse 保留键会被映射到 UI 的会话、用户、标签维度：
    - langfuse_session_id → 同一咨询线程的多轮对话归入同一 session
    - langfuse_user_id → 账号维度，便于按用户排查
    - langfuse_tags → 支持按 agent 模式 / 流式通道筛选

    Args:
        thread_id: 会话线程 ID
        username: 当前登录账号
        member_id: 咨询人 ID（主成员为 None）
        agent_mode: workflow / multiagent
        streaming: 是否流式通道

    Returns:
        可直接放进 config["metadata"] 的字典
    """
    return {
        "langfuse_session_id": thread_id,
        "langfuse_user_id": username,
        "langfuse_tags": [agent_mode, "stream" if streaming else "sync"],
        "agent_mode": agent_mode,
        "member_id": member_id or "",
        "thread_id": thread_id,
    }
