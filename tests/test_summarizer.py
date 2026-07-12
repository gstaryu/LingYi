"""
上下文压缩器测试 - 验证 should_summarize 阈值/冷却 与 summarize_node 的 RemoveMessage 移除。
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from lingyi.agent.memory.summarizer import should_summarize, summarize_node
from tests.stubs import StubLLM


class TestSummarizer:
    """Summarizer 测试套件。"""

    def test_should_not_summarize_short_history(self):
        """短历史不触发压缩。"""
        state = {"messages": [HumanMessage(content="短")], "last_summarized_message_count": 0}
        assert should_summarize(state, threshold=8000) is False

    def test_should_not_summarize_within_cooldown(self):
        """冷却期内（新增不足 6 条）不触发，即使字符数超标。"""
        long = "字" * 10000
        msgs = [HumanMessage(content=long, id=str(i)) for i in range(5)]
        state = {"messages": msgs, "last_summarized_message_count": 0}
        # 5 条 < 冷却 6 条
        assert should_summarize(state, threshold=1000) is False

    def test_should_summarize_when_long_and_enough_new(self):
        """字符数超标且新增足够时触发。"""
        long = "字" * 1000
        msgs = [HumanMessage(content=long, id=str(i)) for i in range(7)]
        state = {"messages": msgs, "last_summarized_message_count": 0}
        assert should_summarize(state, threshold=1000) is True

    async def test_summarize_node_removes_old_messages(self):
        """summarize_node 应返回 RemoveMessage 列表移除旧消息，并保留摘要。"""
        llm = StubLLM(response="摘要：患者发热恶寒。")
        # 7 条消息，保留最后 3 条，移除前 4 条
        msgs = [HumanMessage(content=f"消息{i}", id=str(i)) for i in range(6)]
        msgs.append(AIMessage(content="回复", id="6"))
        state = {"messages": msgs}
        result = await summarize_node(state, llm)

        assert result["summary"] == "摘要：患者发热恶寒。"
        assert result["last_summarized_message_count"] == 3
        # 移除 4 条旧消息（7 - 3）
        removals = result["messages"]
        assert len(removals) == 4
        assert all(isinstance(m, RemoveMessage) for m in removals)
        removed_ids = {m.id for m in removals}
        assert removed_ids == {"0", "1", "2", "3"}

    async def test_summarize_node_skips_when_too_few(self):
        """消息数 <= 3 时不压缩。"""
        llm = StubLLM(response="x")
        state = {"messages": [HumanMessage(content="a", id="1")]}
        result = await summarize_node(state, llm)
        assert result == {}
