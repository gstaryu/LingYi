"""
方剂专家 - 经典方剂推荐及加减。

工具: search_formulas, lookup_herb, search_tcm_classics
输出: {specialist, recommended_formulas, modifications, reasoning}
"""

import logging
from typing import Any

from lingyi.agent.specialists.base import SpecialistBase

logger = logging.getLogger(__name__)


class SpecialistFangji(SpecialistBase):
    """方剂专家 Agent - 据证候推荐经典方剂及加减。"""

    SYSTEM_PROMPT = (
        "你是中医方剂专家。根据辨证结果，推荐经典方剂及加减变化。\n"
        "请先使用工具搜索方剂库和查询药材信息，再给出推荐。\n\n"
        "输出要求：以JSON格式输出，包含以下字段：\n"
        '- "specialist": "方剂"\n'
        '- "recommended_formulas": 推荐方剂名称列表（如["理中丸", "参苓白术散"]）\n'
        '- "modifications": 加减变化说明\n'
        '- "reasoning": 推荐推理过程\n'
        "只输出JSON，不要包含其他解释文字。"
    )
    SPECIALIST_NAME = "方剂"

    async def prefetch(self, state: dict[str, Any]) -> str:
        """预取方剂检索结果（直接调用工具，不经 LLM）。"""
        symptoms = state.get("symptoms", [])
        if not symptoms:
            return ""
        query = " ".join(symptoms)
        return await self._call_tool("search_formulas", {"query": query})

    def _parse_note(self, content: str) -> dict[str, Any]:
        """解析方剂笔记。"""
        data = self._parse_json(content)
        if data is None:
            logger.warning("方剂专家 JSON 解析失败，使用 fallback")
            return {
                "specialist": self.SPECIALIST_NAME,
                "recommended_formulas": [],
                "modifications": "",
                "reasoning": content[:500] if content else "方剂推荐失败",
            }
        formulas = data.get("recommended_formulas", [])
        if not isinstance(formulas, list):
            formulas = [str(formulas)] if formulas else []
        return {
            "specialist": self.SPECIALIST_NAME,
            "recommended_formulas": formulas,
            "modifications": data.get("modifications", ""),
            "reasoning": data.get("reasoning", ""),
        }
