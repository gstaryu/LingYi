from langchain_core.messages import SystemMessage
from agent.state import AgentState
from model_provider import model_manager


# 保留最近 N 条消息不进入摘要（保持对话连贯性）
_KEEP_LAST_N = 3
# 冷却：距离上次摘要至少新增这么多条消息才再次摘要（避免频繁总结）
_COOLDOWN_NEW_MESSAGES = 6


def summarizer_node(state: AgentState):
    """上下文压缩节点（增量摘要）。

    规则：
    - 只总结除最后 _KEEP_LAST_N 条之外的历史。
    - 通过 summarized_until 记录已经总结到的位置，之后只增量总结新增部分。
    - 通过 last_summarized_message_count + 冷却窗口避免频繁触发。
    - 生成摘要后裁剪 messages，让 state 真正变短（回收上下文长度）。

    返回值只包含需要写回图状态的增量字段。
    """

    messages = state.get("messages", []) or []
    total_messages = len(messages)

    # 没有足够的消息，不需要摘要
    if total_messages <= _KEEP_LAST_N:
        return {}

    summary = state.get("summary", "") or ""
    summarized_until = int(state.get("summarized_until", 0) or 0)
    last_summarized_message_count = int(state.get("last_summarized_message_count", 0) or 0)

    # 冷却：新增消息不足则跳过（匹配 test_summarizer.py 的期望行为）
    if total_messages - last_summarized_message_count < _COOLDOWN_NEW_MESSAGES and last_summarized_message_count != 0:
        return {}

    # 本轮允许被摘要覆盖到的上限（排除最后 _KEEP_LAST_N 条）
    target_until = max(0, total_messages - _KEEP_LAST_N)

    # 没有新的可摘要内容（例如刚裁剪过，或重复触发）
    if summarized_until >= target_until:
        return {}

    # 仅摘要增量部分
    history_to_summarize = messages[summarized_until:target_until]
    if not history_to_summarize:
        return {}

    print(f"--- 📥 触发上下文压缩 (消息数: {total_messages}, 增量区间: [{summarized_until}:{target_until}]) ---")

    try:
        llm = model_manager.get_model()

        summary_prompt = """
你是一个专业的中医助手中述员。请将以下对话历史压缩为一段简练的“病历纪要”。
要求保留：
1. 患者已确认的症状。
2. 已经得出的辨证结论（理、法）。
3. 已经开出的方药（方、药）。
去除：所有寒暄、重复问答。
输出格式：直接输出纪要内容。
""".strip()

        # 将既有摘要作为输入，让模型在此基础上“续写/更新”，实现真正的增量摘要
        existing_summary_block = summary.strip() if summary.strip() else "（空）"

        response = llm.invoke(
            [
                SystemMessage(content=summary_prompt),
                SystemMessage(content=f"【既有病历纪要】\n{existing_summary_block}"),
                SystemMessage(content="=== 以下是需要补充进纪要的新增对话片段 ==="),
            ]
            + history_to_summarize
        )

        new_summary = (response.content or "").strip()
        if not new_summary:
            # 摘要为空则不更新，避免污染状态
            return {}

        # 裁剪 messages：丢弃已被摘要覆盖的部分，只保留最后 _KEEP_LAST_N 条
        kept_tail = messages[-_KEEP_LAST_N:] if total_messages >= _KEEP_LAST_N else messages

        return {
            "summary": new_summary,
            "summarized_until": target_until,
            "last_summarized_message_count": total_messages,
            "messages": kept_tail,
        }
    except Exception as e:
        print(f"❌ 摘要生成失败: {e}")
        return {}