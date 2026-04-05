import os
from langchain_core.messages import SystemMessage
from agent.state import AgentState
from model_provider import model_manager


def summarizer_node(state: AgentState):
    """
    上下文压缩节点：当消息过长时，将旧对话压缩为“病历纪要”。
    """
    messages = state.get("messages", [])

    # 设定压缩阈值（测试环境下设为 6，生产环境建议设为 15-20 或按 Token 计算）
    if len(messages) <= 10:
        # 显式返回空字典，确保 LangGraph 不会传递 None 给下游或 Stream 迭代器
        return {}

    print(f"--- 📥 触发上下文压缩 (当前消息数: {len(messages)}) ---")

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
        """

        history_to_summarize = messages[:-3]

        response = llm.invoke([
                                  SystemMessage(content=summary_prompt),
                                  SystemMessage(content="=== 以下是需要总结的历史对话 ===")
                              ] + history_to_summarize)

        new_summary = response.content
        print(f"✅ 生成新摘要: {new_summary[:50]}...")

        return {
            "summary": new_summary
        }
    except Exception as e:
        print(f"❌ 摘要生成失败: {e}")
        return {}