"""
上下文压缩器 - 当对话历史过长时自动压缩为摘要。

设计原则:
- 增量压缩：只压缩旧消息，保留已有摘要并合并
- 冷却机制：需要至少 6 条新消息才触发压缩
- 保留最近 3 条消息不压缩
- 使用 LangGraph RemoveMessage 真实移除旧消息
  （add_messages reducer 是追加/合并语义，返回 recent_messages 并不会替换旧消息；
   必须用 RemoveMessage 按 ID 删除，否则历史永不缩减--这是原实现的 bug）
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, RemoveMessage

logger = logging.getLogger(__name__)

# 冷却阈值：至少需要 N 条新消息才触发压缩
COOLDOWN_MESSAGES = 6

# 压缩时保留的最近消息条数
KEEP_RECENT = 3


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

    # 冷却检查：自上次压缩后需新增足够消息
    last_count = state.get("last_summarized_message_count", 0)
    if len(messages) - last_count < COOLDOWN_MESSAGES:
        return False

    return total_chars > threshold


async def summarize_node(state: dict[str, Any], llm: Any) -> dict[str, Any]:
    """
    压缩上下文节点。

    将旧消息压缩为摘要，用 RemoveMessage 按 ID 移除旧消息，保留最近 KEEP_RECENT 条。
    压缩后 last_summarized_message_count 设为剩余条数，使冷却机制基于压缩后的基数。

    Args:
        state: AgentState
        llm: BaseLLM 实例

    Returns:
        更新后的 messages（RemoveMessage 列表）、summary、last_summarized_message_count
    """
    if not llm:
        return {}

    messages = state.get("messages", [])
    if len(messages) <= KEEP_RECENT:
        return {}

    old_messages = messages[:-KEEP_RECENT]
    recent_messages = messages[-KEEP_RECENT:]

    # 构建压缩 prompt（合并已有摘要）
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
        response = await llm.ainvoke([HumanMessage(content="\n".join(prompt_parts))])
        new_summary = response.strip()
    except Exception as e:
        logger.warning("上下文压缩失败: %s", e)
        return {}

    # 用 RemoveMessage 按 ID 移除旧消息（add_messages reducer 识别 RemoveMessage 并删除）
    # 仅移除有 id 的消息；id=None 的 RemoveMessage 会清空全部，必须过滤
    removals = [RemoveMessage(id=m.id) for m in old_messages if getattr(m, "id", None)]

    return {
        "messages": removals,
        "summary": new_summary,
        # 压缩后剩余 KEEP_RECENT 条，冷却基于此基数计算
        "last_summarized_message_count": KEEP_RECENT,
    }
