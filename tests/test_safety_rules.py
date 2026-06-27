"""
安全规则引擎测试 — 纯单元测试，无 API 依赖。
"""

import pytest
from lingyi.safety.rules import SafetyEngine


class TestSafetyEngine:
    """SafetyEngine 测试套件。"""

    def test_safe_prescription(self, safety_engine: SafetyEngine):
        """安全药方应通过校验。"""
        herbs = ["黄芪", "当归", "白术", "茯苓"]
        is_safe, msg = safety_engine.check_prescription(herbs)
        assert is_safe is True
        assert msg is None

    def test_eighteen_antagonism_detected(self, safety_engine: SafetyEngine):
        """十八反应被检测到。"""
        herbs = ["甘草", "海藻"]
        is_safe, msg = safety_engine.check_prescription(herbs)
        assert is_safe is False
        assert "甘草" in msg
        assert "海藻" in msg

    def test_nineteen_inhibition_detected(self, safety_engine: SafetyEngine):
        """十九畏应被检测到。"""
        herbs = ["丁香", "郁金"]
        is_safe, msg = safety_engine.check_prescription(herbs)
        assert is_safe is False
        assert "丁香" in msg
        assert "郁金" in msg

    def test_keyword_matching(self, safety_engine: SafetyEngine):
        """应支持关键词包含匹配。"""
        herbs = ["生甘草", "海藻"]
        is_safe, msg = safety_engine.check_prescription(herbs)
        assert is_safe is False

    def test_bidirectional_check(self, safety_engine: SafetyEngine):
        """禁忌应双向检测。"""
        herbs_a = ["甘草", "海藻"]
        herbs_b = ["海藻", "甘草"]
        is_safe_a, _ = safety_engine.check_prescription(herbs_a)
        is_safe_b, _ = safety_engine.check_prescription(herbs_b)
        assert is_safe_a == is_safe_b == False

    def test_empty_prescription(self, safety_engine: SafetyEngine):
        """空药方应安全。"""
        is_safe, msg = safety_engine.check_prescription([])
        assert is_safe is True

    def test_single_herb(self, safety_engine: SafetyEngine):
        """单味药应安全。"""
        is_safe, _ = safety_engine.check_prescription(["黄芪"])
        assert is_safe is True

    def test_get_rules_text(self, safety_engine: SafetyEngine):
        """规则文本应包含十八反和十九畏。"""
        text = safety_engine.get_rules_text()
        assert "十八反" in text
        assert "十九畏" in text
        assert "甘草" in text
