"""
辨证专家 - 八纲/脏腑/六经辨证。

工具: search_tcm_classics, get_patient_profile
输出: {specialist, syndrome, reasoning, confidence}
"""

import logging
from typing import Any

from lingyi.agent.specialists.base import SpecialistBase

logger = logging.getLogger(__name__)


class SpecialistBianzheng(SpecialistBase):
    """辨证专家 Agent - 根据症状+体质+古籍给出证候诊断。"""

    SYSTEM_PROMPT = (
        "你是中医辨证专家。根据患者症状、体质和古籍检索结果，进行八纲辨证、脏腑辨证或六经辨证。\n"
        "请先使用工具检索相关古籍和患者画像，再给出辨证结论。\n\n"
        "输出要求：以JSON格式输出，包含以下字段：\n"
        '- "specialist": "辨证"\n'
        '- "syndrome": 证候名称（如"脾胃虚寒证"）\n'
        '- "reasoning": 辨证推理过程（简述病机分析）\n'
        '- "confidence": 置信度（0-1的浮点数）\n'
        "只输出JSON，不要包含其他解释文字。"
    )
    SPECIALIST_NAME = "辨证"

    async def prefetch(self, state: dict[str, Any]) -> str:
        """预取中医古籍检索结果（直接调用工具，不经 LLM）。"""
        symptoms = state.get("symptoms", [])
        if not symptoms:
            return ""
        query = " ".join(symptoms)
        return await self._call_tool("search_tcm_classics", {"query": query})

    def _parse_note(self, content: str) -> dict[str, Any]:
        """解析辨证笔记。"""
        data = self._parse_json(content)
        if data is None:
            logger.warning("辨证专家 JSON 解析失败，使用 fallback")
            return {
                "specialist": self.SPECIALIST_NAME,
                "syndrome": "",
                "reasoning": content[:500] if content else "辨证分析失败",
                "confidence": 0.0,
            }
        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        return {
            "specialist": self.SPECIALIST_NAME,
            "syndrome": data.get("syndrome", ""),
            "reasoning": data.get("reasoning", ""),
            "confidence": confidence,
        }
