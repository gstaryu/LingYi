"""
处方技能 - 中医方药推荐与安全校验。

根据辨证结果生成处方建议，并通过 SafetyEngine 进行配伍禁忌校验。
若检测到禁忌，将错误信息反馈给 LLM 要求修正。
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import BaseMessage

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class TreatmentSkill(BaseSkill):
    """
    处方技能节点。

    生成处方建议后，自动调用 SafetyEngine 进行十八反十九畏校验。
    若检测到配伍禁忌，将冲突信息反馈给 LLM 要求重写。
    """

    def __init__(
        self,
        llm: Any = None,
        safety_engine: Any = None,
        max_history: int = 2,
        max_retries: int = 3,
    ):
        """
        初始化处方技能。

        Args:
            llm: LLM 实例
            safety_engine: SafetyEngine 实例，用于配伍禁忌校验
            max_history: 携带的历史对话轮次
            max_retries: 安全校验失败时的最大重试次数
        """
        super().__init__(llm=llm)
        self.safety_engine = safety_engine
        self.max_history = max_history
        self.max_retries = max_retries

    def build_messages(self, state: dict[str, Any]) -> list[BaseMessage]:
        """构建处方消息列表，注入辨证结果、安全规则等上下文。"""
        # 主 system prompt + 安全规则（合并为一条 system 消息）
        prompt_parts: list[str] = []
        if self.system_prompt:
            prompt_parts.append(self.system_prompt)
        if self.safety_engine:
            prompt_parts.append(
                f"\n\n【配伍禁忌规则 - 必须严格遵守】\n{self.safety_engine.get_rules_text()}"
            )
        system_prompt = "\n".join(prompt_parts)

        # 上下文：辨证结果、患者画像、安全错误反馈
        context_parts: list[str] = []

        diagnosis = state.get("diagnosis", "")
        if diagnosis:
            context_parts.append(f"辨证结果:\n{diagnosis}")

        profile = state.get("patient_profile", {})
        if profile:
            context_parts.append(
                f"患者画像: 体质={profile.get('constitution', '未知')}, "
                f"过敏={profile.get('allergies', '无')}"
            )

        safety_errors = state.get("safety_errors", "")
        if safety_errors:
            context_parts.append(
                f"【安全校验失败 - 必须修正以下问题】\n{safety_errors}\n"
                "请删除或替换存在配伍禁忌的药材，重新生成处方。"
            )

        messages = self._build_system_messages(system_prompt, context_parts)
        messages.extend(self._history_to_messages(state.get("messages", []), self.max_history))
        return messages

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        生成处方并进行安全校验。

        Returns:
            更新后的 messages, treatment_plan, safety_errors
        """
        if not self.llm:
            return {"treatment_plan": "无法生成处方：LLM 未配置"}

        messages = self.build_messages(state)
        try:
            response = await self.llm.ainvoke(messages)
        except Exception as e:
            logger.error("处方 LLM 调用失败: %s", e)
            return {"treatment_plan": f"处方生成失败: {e}"}

        # 安全校验
        if self.safety_engine:
            herbs = self._extract_herbs(response)
            if herbs:
                is_safe, error_msg = self.safety_engine.check_prescription(herbs)
                if not is_safe:
                    logger.warning("处方安全校验失败: %s", error_msg)
                    return {
                        "messages": [{"role": "assistant", "content": response}],
                        "treatment_plan": response,
                        "safety_errors": error_msg,
                        "safety_retry_count": state.get("safety_retry_count", 0) + 1,
                    }

        return {
            "messages": [{"role": "assistant", "content": response}],
            "treatment_plan": response,
            "safety_errors": None,
            "has_provided_treatment": True,
        }

    def _extract_herbs(self, response: str) -> list[str]:
        """从 LLM 输出中提取药材名称列表（与 treatment.md 的 herb_names JSON 契约对齐）。"""
        # 尝试从 ```json ... ``` 代码块中提取
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, dict) and "herb_names" in data:
                    return data["herb_names"]
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        # 尝试从文本中提取含 herb_names 的 JSON 对象
        json_match = re.search(r'\{[^{}]*"herb_names"[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data.get("herb_names", [])
            except json.JSONDecodeError:
                pass

        return []


def safety_check_logic(state: dict[str, Any], max_retries: int = 3) -> str:
    """
    处方安全校验路由逻辑。

    Returns:
        "re_treatment" - 需要重新生成处方
        "safe_to_end" - 处方安全，可以结束
    """
    safety_errors = state.get("safety_errors")
    retry_count = state.get("safety_retry_count", 0)

    if safety_errors and retry_count < max_retries:
        return "re_treatment"
    return "safe_to_end"
