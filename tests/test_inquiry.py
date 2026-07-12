"""
问诊技能测试 - 意图识别、症状提取、追问上限控制、结构化输出与回退。

使用 StubLLM(structured=InquiryResult(...)) 验证结构化输出路径，
并验证 LLM 不支持结构化输出时的 JSON 回退与 consult 降级（原 bug：降级为 chat 误吞 diagnose）。
"""

import pytest
from langchain_core.messages import HumanMessage

from lingyi.agent.skills.inquiry import InquiryResult, InquirySkill
from tests.stubs import StubLLM


class TestInquirySkill:
    """InquirySkill 测试套件。"""

    async def test_consult_increments_count(self):
        """consult 意图应递增 inquiry_count 并保留症状与 response。"""
        llm = StubLLM(
            structured=InquiryResult(
                intent_type="consult", is_complete=False, symptoms=["发热"], response="怕冷吗？"
            )
        )
        skill = InquirySkill(llm=llm, max_followups=2)
        state = {"messages": [HumanMessage(content="我发烧了")], "inquiry_count": 0}
        result = await skill.execute(state)
        assert result["intent_type"] == "consult"
        assert result["inquiry_count"] == 1
        assert "发热" in result["symptoms"]
        assert result["messages"][0]["content"] == "怕冷吗？"

    async def test_diagnose_routes_without_advice(self):
        """diagnose 意图应设置 intent，response 为过渡语（不含医疗建议），不递增计数。"""
        llm = StubLLM(
            structured=InquiryResult(
                intent_type="diagnose",
                is_complete=True,
                symptoms=["舌苔厚"],
                response="好的，我来为您辨证分析",
            )
        )
        skill = InquirySkill(llm=llm)
        state = {"messages": [HumanMessage(content="舌苔白厚")], "inquiry_count": 0}
        result = await skill.execute(state)
        assert result["intent_type"] == "diagnose"
        assert "辨证" in result["messages"][0]["content"]
        assert "inquiry_count" not in result

    async def test_max_followups_forces_diagnose(self):
        """达到追问上限时应强制 diagnose，不生成追问。"""
        llm = StubLLM(structured=InquiryResult(intent_type="consult", response="还在问？"))
        skill = InquirySkill(llm=llm, max_followups=2)
        state = {"messages": [HumanMessage(content="继续")], "inquiry_count": 2}
        result = await skill.execute(state)
        assert result["intent_type"] == "diagnose"
        assert "inquiry_count" not in result

    async def test_gratitude_downgrades_to_chat(self):
        """感谢词应将意图降级为 chat。"""
        llm = StubLLM(structured=InquiryResult(intent_type="diagnose", response="不客气"))
        skill = InquirySkill(llm=llm)
        state = {"messages": [HumanMessage(content="谢谢医生")], "inquiry_count": 0}
        result = await skill.execute(state)
        assert result["intent_type"] == "chat"

    async def test_no_llm_returns_chat(self):
        """未注入 LLM 时安全返回 chat 意图。"""
        skill = InquirySkill(llm=None)
        result = await skill.execute({"messages": [HumanMessage(content="你好")]})
        assert result["intent_type"] == "chat"

    async def test_json_fallback_when_structured_unsupported(self):
        """LLM 不支持结构化输出时，回退 JSON 解析，仍能识别 diagnose。"""
        class _NoStructuredLLM(StubLLM):
            def with_structured_output(self, schema):
                raise NotImplementedError("不支持")

        llm = _NoStructuredLLM(
            response='{"intent_type":"diagnose","symptoms":["发热"],"response":"好的"}'
        )
        skill = InquirySkill(llm=llm)
        state = {"messages": [HumanMessage(content="我发烧")], "inquiry_count": 0}
        result = await skill.execute(state)
        assert result["intent_type"] == "diagnose"
        assert "发热" in result["symptoms"]

    async def test_json_parse_failure_degrades_to_consult(self):
        """JSON 解析失败时应降级为 consult（而非 chat），避免误吞 diagnose 流程。"""
        class _NoStructuredLLM(StubLLM):
            def with_structured_output(self, schema):
                raise NotImplementedError("不支持")

        llm = _NoStructuredLLM(response="这完全不是 JSON")
        skill = InquirySkill(llm=llm)
        state = {"messages": [HumanMessage(content="不舒服")], "inquiry_count": 0}
        result = await skill.execute(state)
        assert result["intent_type"] == "consult"  # 关键：不是 chat

    async def test_post_treatment_adjustment_not_short_circuited(self):
        """已提供治疗后，即使 inquiry_count 达上限，也不应强制 diagnose 跳过分类；
        需正常调用 LLM 提取新信息（如过敏）并交由路由重新出方。"""
        llm = StubLLM(
            structured=InquiryResult(
                intent_type="diagnose",
                is_complete=True,
                symptoms=["茯苓过敏"],
                response="好的，我来为您调整方案",
            )
        )
        skill = InquirySkill(llm=llm, max_followups=2)
        state = {
            "messages": [HumanMessage(content="我对茯苓过敏")],
            "inquiry_count": 2,  # 已达上限
            "has_provided_treatment": True,  # 已出过方
        }
        result = await skill.execute(state)
        # 未被 max_followups 短路：走了 LLM，提取了过敏，意图为 diagnose（将重新进 treatment）
        assert result["intent_type"] == "diagnose"
        assert "茯苓过敏" in result["symptoms"]
        assert "调整" in result["messages"][0]["content"]
