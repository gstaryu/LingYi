"""
上下文压缩器 — 当对话历史过长时自动压缩为摘要。

设计原则:
- 增量压缩：只压缩新产生的消息，保留已有摘要
- 冷却机制：需要至少 6 条新消息才触发压缩
- 保留最近 3 条消息不压缩
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 冷却阈值：至少需要 N 条新消息才触发压缩
COOLDOWN_MESSAGES = 6


def should_summarize(state: dict[str, Any], threshold: int = 8000) -> bool:
    """
    判断是否需要压缩上下文。

    Args:
        state: AgentState
        threshold: 字符数阈值

    Returns:
        True 表示需要压缩
    """
    messages = state.get("messages", [])
    if not messages:
        return False

    # 计算消息总字符数
    total_chars = sum(len(getattr(m, "content", "")) for m in messages)

    # 冷却检查
    last_count = state.get("last_summarized_message_count", 0)
    if len(messages) - last_count < COOLDOWN_MESSAGES:
        return False

    return total_chars > threshold


async def summarize_node(state: dict[str, Any], llm: Any) -> dict[str, Any]:
    """
    压缩上下文节点。

    将旧消息压缩为摘要，保留最近 3 条消息。

    Args:
        state: AgentState
        llm: BaseLLM 实例

    Returns:
        更新后的 messages 和 summary
    """
    if not llm:
        return {}

    messages = state.get("messages", [])
    if len(messages) <= 3:
        return {}

    # 保留最近 3 条消息
    keep_count = 3
    old_messages = messages[:-keep_count]
    recent_messages = messages[-keep_count:]

    # 构建压缩 prompt
    old_text = "\n".join(
        f"{getattr(m, 'type', 'user')}: {getattr(m, 'content', '')}"
        for m in old_messages
    )

    existing_summary = state.get("summary", "")

    prompt_parts = [
        "你是一个医疗记录摘要助手。请将以下对话历史压缩为简洁的病历摘要。",
        "保留关键信息：症状、辨证结果、处方建议、患者反馈。",
        "忽略寒暄和无关内容。",
    ]
    if existing_summary:
        prompt_parts.append(f"\n已有摘要:\n{existing_summary}")

    prompt_parts.append(f"\n对话历史:\n{old_text}")
    prompt_parts.append("\n请输出合并后的完整摘要（不超过 500 字）:")

    try:
        response = await llm.ainvoke([{"role": "user", "content": "\n".join(prompt_parts)}])
        new_summary = response.strip()
    except Exception as e:
        logger.warning("上下文压缩失败: %s", e)
        return {}

    return {
        "messages": recent_messages,
        "summary": new_summary,
        "last_summarized_message_count": len(messages),
    }
