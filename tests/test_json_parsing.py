"""
JSON 解析测试 — 验证从 LLM 输出中提取 JSON 的能力。
使用 BaseSkill.parse_json_response() 公共静态方法。
"""

import json
import pytest
from lingyi.agent.skills.base import BaseSkill


class TestJsonParsing:
    """JSON 提取测试套件。"""

    def test_direct_json(self):
        """直接 JSON 应被解析。"""
        response = '{"intent_type": "diagnose", "symptoms": ["头痛"]}'
        result = BaseSkill.parse_json_response(response)
        assert result["intent_type"] == "diagnose"
        assert "头痛" in result["symptoms"]

    def test_fenced_json(self):
        """代码块包裹的 JSON 应被解析。"""
        response = '```json\n{"intent_type": "chat", "symptoms": []}\n```'
        result = BaseSkill.parse_json_response(response)
        assert result["intent_type"] == "chat"

    def test_json_in_text(self):
        """嵌入在文本中的 JSON 应被解析。"""
        response = '根据您的描述，我认为 {"intent_type": "consult", "symptoms": ["发热"]} 是合适的。'
        result = BaseSkill.parse_json_response(response)
        assert result["intent_type"] == "consult"

    def test_invalid_json_fallback(self):
        """无效 JSON 应返回兜底结果。"""
        response = "这不是一个 JSON 响应"
        fallback = {"response": response, "intent_type": "chat", "symptoms": []}
        result = BaseSkill.parse_json_response(response, fallback=fallback)
        assert result["intent_type"] == "chat"
        assert "response" in result

    def test_empty_string(self):
        """空字符串应返回默认空字典。"""
        result = BaseSkill.parse_json_response("")
        assert result == {}

    def test_custom_fallback(self):
        """自定义兜底值应被正确返回。"""
        result = BaseSkill.parse_json_response("invalid", fallback={"default": True})
        assert result == {"default": True}
