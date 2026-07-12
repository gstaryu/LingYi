"""
前置安全审查技能 — 在问诊前检测用户输入中的配伍禁忌意图。

作为图中的前置拦截节点，如果用户主动要求添加存在配伍禁忌的药材，
系统直接拒绝响应并输出警告。
"""

import logging
from typing import Any

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SafetyGuardSkill(BaseSkill):
    """
    前置安全审查节点。

    使用 LLM 检测用户输入中是否包含配伍禁忌请求。
    若检测到违规，设置 intent_type="safety_rejected" 并生成拒绝消息。
    """

    def __init__(self, llm: Any = None):
        """
        初始化安全审查技能。

        Args:
            llm: LLM 实例
        """
        super().__init__(llm=llm)

    def build_messages(self, state: dict[str, Any]) -> list[dict[str, str]]:
        """构建安全审查消息列表。"""
        messages: list[dict[str, str]] = []

        # System prompt
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 取最近 4 条消息用于审查
        history = state.get("messages", [])
        recent = history[-4:] if history else []
        for msg in recent:
            role = getattr(msg, "type", "user")
            content = getattr(msg, "content", "")
            if role in ("human", "user"):
                messages.append({"role": "user", "content": content})
            elif role in ("ai", "assistant"):
                messages.append({"role": "assistant", "content": content})

        return messages

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        执行前置安全审查。

        Args:
            state: AgentState

        Returns:
            若安全: 空字典（继续正常流程）
            若违规: intent_type="safety_rejected" + 拒绝消息
        """
        if not self.llm:
            return {}

        # 关键词预检：用户消息中没有药材相关词汇时，直接放行，不调 LLM
        last_user_msg = ""
        for msg in reversed(state.get("messages", [])):
            if getattr(msg, "type", "") in ("human", "user"):
                last_user_msg = getattr(msg, "content", "")
                break
        herb_keywords = (
            "甘草", "海藻", "乌头", "半夏", "贝母", "藜芦", "人参", "附子",
            "硫黄", "水银", "巴豆", "丁香", "芒硝", "肉桂", "桂枝",
            "开方", "开药", "处方", "药材", "中药", "配伍", "反", "畏",
        )
        if not any(kw in last_user_msg for kw in herb_keywords):
            logger.debug("安全审查: 用户消息无药材关键词，跳过 LLM 调用")
            return {}

        messages = self.build_messages(state)
        try:
            response = await self.llm.ainvoke(messages)
        except Exception as e:
            logger.error("安全审查 LLM 调用失败: %s", e)
            return {}  # 调用失败时放行

        # 解析响应
        parsed = self.parse_json_response(response, fallback={"has_violation": False})
        has_violation = parsed.get("has_violation", False)

        if has_violation:
            violation_reason = parsed.get("violation_reason", "检测到配伍禁忌")
            rejection_msg = (
                f"⚠️ 安全警告：{violation_reason}\n\n"
                "您的请求涉及中药配伍禁忌（十八反/十九畏），系统无法执行此操作。\n"
                "中药配伍禁忌是中医用药的基本安全准则，违反可能导致严重不良反应。\n\n"
                "如有疑问，请咨询专业中医师。"
            )
            logger.warning("安全审查拦截: %s", violation_reason)
            return {
                "messages": [{"role": "assistant", "content": rejection_msg}],
                "intent_type": "safety_rejected",
                "safety_violation_msg": violation_reason,
            }

        return {}

