"""
本草专家 - 药材性味用量与安全核查。

工具: lookup_herb, check_herb_safety, web_search
输出: {specialist, herb_notes, safety_warnings, reasoning}
"""

import logging
from typing import Any

from lingyi.agent.specialists.base import SpecialistBase

logger = logging.getLogger(__name__)


class SpecialistBencao(SpecialistBase):
    """本草专家 Agent - 核查药材性味用量与安全（含配伍禁忌）。"""

    SYSTEM_PROMPT = (
        "你是本草专家。核查药材的性味归经、用法用量与安全性，包括配伍禁忌。\n"
        "请先使用工具查询药材信息和校验配伍安全，再给出结论。\n\n"
        "输出要求：以JSON格式输出，包含以下字段：\n"
        '- "specialist": "本草"\n'
        '- "herb_notes": 药材备注列表（每项为字典，含 name/nature/dosage 等键）\n'
        '- "safety_warnings": 安全警告列表（字符串列表）\n'
        '- "reasoning": 推理过程\n'
        "只输出JSON，不要包含其他解释文字。"
    )
    SPECIALIST_NAME = "本草"

    async def prefetch(self, state: dict[str, Any]) -> str:
        """预取与症状相关的本草数据（直接调用工具，不经 LLM）。

        按每个症状关键词分别搜索本草库，合并结果，使本草专家基于结构化数据
        （性味/归经/功效/用量/禁忌）而非纯 LLM 记忆作答。
        """
        symptoms = state.get("symptoms", [])
        if not symptoms:
            return ""
        parts = []
        for symptom in symptoms[:3]:  # 最多查 3 个症状关键词
            data = await self._call_tool("search_herbs", {"query": symptom})
            if data and data != "[]" and len(data) > 2:
                parts.append(f"[症状「{symptom}」相关药材]\n{data}")
        return "\n\n".join(parts)

    def _parse_note(self, content: str) -> dict[str, Any]:
        """解析本草笔记。"""
        data = self._parse_json(content)
        if data is None:
            logger.warning("本草专家 JSON 解析失败，使用 fallback")
            return {
                "specialist": self.SPECIALIST_NAME,
                "herb_notes": [],
                "safety_warnings": [],
                "reasoning": content[:500] if content else "本草核查失败",
            }
        herb_notes = data.get("herb_notes", [])
        if not isinstance(herb_notes, list):
            herb_notes = []
        safety_warnings = data.get("safety_warnings", [])
        if not isinstance(safety_warnings, list):
            safety_warnings = [str(safety_warnings)] if safety_warnings else []
        return {
            "specialist": self.SPECIALIST_NAME,
            "herb_notes": herb_notes,
            "safety_warnings": safety_warnings,
            "reasoning": data.get("reasoning", ""),
        }
