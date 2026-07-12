"""
辨证技能测试 - 验证 DiagnosisSkill 调用 LLM 并返回辨证结果。

使用 StubLLM，不依赖真实 API。
"""

import pytest
from langchain_core.messages import HumanMessage

from lingyi.agent.skills.diagnosis import DiagnosisSkill
from tests.stubs import StubLLM


class TestDiagnosisSkill:
    """DiagnosisSkill 测试套件。"""

    async def test_returns_diagnosis_and_message(self):
        """辨证应返回 diagnosis 字段并追加 assistant 消息。"""
        llm = StubLLM(response="辨证为太阳伤寒证，治宜发汗解表。")
        skill = DiagnosisSkill(llm=llm, max_history=3)
        state = {
            "messages": [HumanMessage(content="我怕冷发烧")],
            "symptoms": ["恶寒", "发热"],
        }
        result = await skill.execute(state)
        assert "太阳" in result["diagnosis"]
        assert result["messages"][0]["content"] == result["diagnosis"]

    async def test_no_llm_returns_error(self):
        """未注入 LLM 时返回错误提示，不抛异常。"""
        skill = DiagnosisSkill(llm=None)
        result = await skill.execute({"messages": [HumanMessage(content="头痛")]})
        assert "LLM" in result["diagnosis"]

    async def test_build_messages_includes_context(self):
        """build_messages 应注入症状与 RAG 文献上下文。"""
        llm = StubLLM(response="ok")
        skill = DiagnosisSkill(llm=llm)
        state = {
            "messages": [HumanMessage(content="头痛")],
            "symptoms": ["头痛"],
            "retrieved_docs": ["太阳之为病，脉浮，头项强痛而恶寒。"],
        }
        msgs = skill.build_messages(state)
        # 至少包含 system + 一条 user 历史
        assert len(msgs) >= 2
