"""
处方技能测试 - 验证 TreatmentSkill 生成处方并进行安全校验。

使用 StubLLM + 真实 SafetyEngine（纯规则，无 API 依赖）。
"""

import pytest

from lingyi.agent.skills.treatment import TreatmentSkill
from lingyi.safety.rules import SafetyEngine
from tests.stubs import StubLLM


class TestTreatmentSkill:
    """TreatmentSkill 测试套件。"""

    @pytest.fixture
    def safety_engine(self) -> SafetyEngine:
        return SafetyEngine()

    async def test_safe_prescription(self, safety_engine):
        """无配伍禁忌的处方应通过校验，标记 has_provided_treatment。"""
        llm = StubLLM(response="处方：桂枝汤\n```json\n{\"herb_names\": [\"桂枝\", \"白芍\"]}\n```")
        skill = TreatmentSkill(llm=llm, safety_engine=safety_engine, max_retries=3)
        result = await skill.execute({"messages": [], "diagnosis": "太阳中风证"})
        assert result["safety_errors"] is None
        assert result["has_provided_treatment"] is True

    async def test_unsafe_prescription_triggers_safety_error(self, safety_engine):
        """含十八反药对（甘草+海藻）的处方应被拦截，设置 safety_errors。"""
        llm = StubLLM(response="处方\n```json\n{\"herb_names\": [\"甘草\", \"海藻\"]}\n```")
        skill = TreatmentSkill(llm=llm, safety_engine=safety_engine, max_retries=3)
        result = await skill.execute({"messages": [], "diagnosis": "测试"})
        assert result["safety_errors"] is not None
        assert "甘草" in result["safety_errors"]
        assert result["safety_retry_count"] == 1

    async def test_extract_herbs_from_fenced_json(self, safety_engine):
        """_extract_herbs 应从 ```json 代码块提取 herb_names。"""
        skill = TreatmentSkill(llm=None, safety_engine=safety_engine)
        resp = '建议\n```json\n{"herb_names": ["黄芪", "当归"]}\n```'
        herbs = skill._extract_herbs(resp)
        assert herbs == ["黄芪", "当归"]

    async def test_extract_herbs_empty(self, safety_engine):
        """无 JSON 块时应返回空列表。"""
        skill = TreatmentSkill(llm=None, safety_engine=safety_engine)
        assert skill._extract_herbs("纯文本处方，无 JSON") == []
