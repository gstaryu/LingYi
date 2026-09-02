"""
前置安全审查技能 — 在问诊前检测用户输入中的配伍禁忌意图。

作为图中的前置拦截节点，如果用户主动要求添加存在配伍禁忌的药材，
系统直接拒绝响应并输出警告。
"""

import logging
import re
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SafetyGuardResult(BaseModel):
    """安全审查结构化输出。"""

    has_violation: bool = Field(description="是否检测到配伍禁忌意图")
    violation_reason: str = Field(default="", description="违规理由")


class SafetyGuardSkill(BaseSkill):
    """
    前置安全审查节点。

    使用 LLM 检测用户输入中是否包含配伍禁忌请求。
    若检测到违规，设置 intent_type="safety_rejected" 并生成拒绝消息。
    """

    def __init__(self, llm: Any = None, fail_mode: str = "closed"):
        """
        初始化安全审查技能。

        Args:
            llm: LLM 实例
            fail_mode: LLM 调用异常时的失败策略
                       "closed"（默认）- 保守拒绝，保障用药安全
                       "open" - 放行（仅用于排障/测试）
        """
        super().__init__(llm=llm)
        self.fail_mode = fail_mode

    def build_messages(self, state: dict[str, Any]) -> list[BaseMessage]:
        """构建安全审查消息列表（system prompt + 最近约 2 轮对话）。"""
        messages = self._build_system_messages(self.system_prompt, [])
        # 取最近 4 条消息（约 2 轮，max_history=2 -> 截取最后 4 条）用于审查
        messages.extend(self._history_to_messages(state.get("messages", []), max_history=2))
        return messages

    async def _evaluate_safety(
        self, messages: list[BaseMessage]
    ) -> tuple[bool, str]:
        """
        评估用户输入是否包含配伍禁忌意图。

        优先用结构化输出（function_calling）；不支持时回退到 JSON 解析。

        Returns:
            (has_violation, violation_reason)
        """
        try:
            structured = self.llm.with_structured_output(SafetyGuardResult)
            result = await structured.ainvoke(messages)
            return bool(result.has_violation), result.violation_reason or ""
        except NotImplementedError:
            response = await self.llm.ainvoke(messages)
            parsed = self.parse_json_response(response, fallback={"has_violation": False})
            return bool(parsed.get("has_violation", False)), parsed.get(
                "violation_reason", ""
            )

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
        # 危重症信号词：命中即确定性引导就医（不经 LLM，100% 拦截）
        critical_match = re.search(
            r"咯血|咳血|呕血|大口吐血|惊厥|抽搐|昏迷|意识不清|意识模糊|说胡话|谵妄"
            r"|压榨(样|感|样疼痛)|板状腹|硬得像板|肚子硬|口唇发紫|喘憋|呼吸骤停|心跳骤停"
            r"|脑梗|中风|中毒|内出血",
            last_user_msg,
        )
        if critical_match:
            logger.warning("安全审查: 命中危重症信号词「%s」，确定性引导就医", critical_match.group(0))
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": (
                            "🚨 您描述的情况可能属于急重症，请立即前往医院急诊或拨打 120，"
                            "切勿延误。线上问诊无法替代急救处置，也不要自行服用药物（包括丹参粉、"
                            "安宫牛黄丸等\"急救\"中药）掩盖症状。"
                        ),
                    }
                ],
                "intent_type": "safety_rejected",
                "safety_violation_msg": f"危重症信号词命中: {critical_match.group(0)}",
            }
        if not any(kw in last_user_msg for kw in herb_keywords):
            logger.debug("安全审查: 用户消息无药材关键词，跳过 LLM 调用")
            return {}

        messages = self.build_messages(state)
        try:
            has_violation, violation_reason = await self._evaluate_safety(messages)
        except Exception as e:
            logger.error("安全审查 LLM 调用失败: %s", e)
            if self.fail_mode == "closed":
                # fail-closed：审查服务不可用时保守拒绝，保障用药安全
                logger.warning("安全审查 fail-closed：拒绝请求（fail_mode=closed）")
                return {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": (
                                "⚠️ 安全审查服务暂时不可用，为保障用药安全，"
                                "系统暂不处理该请求。请稍后重试或咨询专业中医师。"
                            ),
                        }
                    ],
                    "intent_type": "safety_rejected",
                    "safety_violation_msg": "安全审查服务不可用（fail-closed）",
                }
            return {}  # open 模式：放行

        if has_violation:
            if not violation_reason:
                violation_reason = "检测到配伍禁忌"
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

