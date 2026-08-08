"""
对抗安全审查者（Phase 3）- 在确定性 SafetyEngine 硬校验之前提供智能审查层。

设计要点:
- SafetyReviewerAgent 继承 SpecialistBase，单次 LLM 调用 + 预计算安全校验
- 工具: check_herb_safety（配伍禁忌），在 LLM 调用前 **直接** 执行（确定性，无 LLM）
- 扮演对抗性批评者角色，尽力发现处方安全问题
- 双重防御: 智能审查者（本模块）+ 确定性 SafetyEngine 硬校验（safety_check 节点）
- 审查者不通过时回退 synthesis 重生成；重试耗尽则交由 SafetyEngine 硬校验裁决
- 依赖注入: chat_model 通过构造函数注入，测试用 StubChatModel
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from lingyi.agent.specialists.base import SpecialistBase

logger = logging.getLogger(__name__)


# ==================== 结构化输出模型 ====================


class SafetyReviewResult(BaseModel):
    """对抗安全审查结果。"""

    approved: bool = Field(description="是否批准处方")
    issues: list[str] = Field(default_factory=list, description="发现的安全问题列表")
    suggestions: str = Field(default="", description="修改建议")


# ==================== 药材提取（与 graph_multiagent._extract_herbs 逻辑一致） ====================


def _extract_herbs(text: str) -> list[str]:
    """从治疗计划文本中提取药材名称列表。"""
    if not text:
        return []
    # 尝试从 ```json ... ``` 代码块中提取
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
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
    json_match = re.search(r'\{[^{}]*"herb_names"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return data.get("herb_names", [])
        except json.JSONDecodeError:
            pass
    return []


# ==================== 路由函数 ====================


def reviewer_router(state: dict[str, Any], max_retries: int = 3) -> str:
    """
    对抗审查者路由逻辑（条件边函数）。

    Returns:
        "safety_check" - 审查通过或重试耗尽，交由确定性硬校验裁决
        "synthesis" - 审查不通过且重试未耗尽，回退 synthesis 重生成
    """
    if state.get("reviewer_approved", False):
        return "safety_check"

    retry_count = state.get("reviewer_retry_count", 0)
    if retry_count < max_retries:
        return "synthesis"

    # 重试耗尽，交由 SafetyEngine 硬校验做最终裁决（fail-open to deterministic gate）
    logger.warning("对抗审查者重试耗尽（%d/%d），交由硬校验裁决", retry_count, max_retries)
    return "safety_check"


# ==================== 对抗安全审查者 Agent ====================


class SafetyReviewerAgent(SpecialistBase):
    """
    对抗安全审查者 Agent - 单次 LLM 调用 + 预计算安全校验。

    扮演对抗性批评者角色，在 LLM 调用前直接执行 check_herb_safety 工具核查处方安全，
    将确定性校验结果注入 prompt，再由 LLM 综合判断。
    审查通过 -> 路由到 safety_check 硬校验（双重防御）。
    审查不通过 -> 回退 synthesis 重生成（携带 safety_errors 反馈）。
    """

    # 基础审查 prompt（不涉及妊娠检查--妊娠/哺乳期由处方声明免责，不在审查流程内）
    SYSTEM_PROMPT = (
        "你是中医处方安全审查官，扮演对抗性批评者角色。\n"
        "你的职责是尽力发现处方中的安全问题：十八反/十九畏配伍禁忌、"
        "体质禁忌、剂量风险。\n\n"
        "工作流程：\n"
        "1. 调用 check_herb_safety 工具核查配伍禁忌\n"
        "2. 调用 lookup_herb 工具了解药材的禁忌信息\n"
        "3. 综合分析后给出审查结论\n\n"
        "审查原则：\n"
        "- 只有确认无安全问题才批准\n"
        "- 有任何疑虑一律不批准并给出修改建议\n"
        "- 患者状态以上下文【患者画像】为准，不得臆测患者未提及的情况\n\n"
        "输出要求：以JSON格式输出审查结果，包含以下字段：\n"
        '- "approved": 布尔值，是否批准\n'
        '- "issues": 字符串列表，发现的安全问题\n'
        '- "suggestions": 字符串，修改建议\n'
        "只输出JSON，不要包含其他解释文字。"
    )
    SPECIALIST_NAME = "安全审查官"

    def __init__(
        self,
        chat_model: Any,
        tools: list | None = None,
        system_prompt: str | None = None,
    ):
        """
        初始化对抗安全审查者。

        Args:
            chat_model: ChatOpenAI 实例（或支持 bind_tools 的 BaseChatModel）
            tools: 审查工具子集（check_herb_safety, lookup_herb）
            system_prompt: 审查者系统提示词（默认用 SYSTEM_PROMPT）
        """
        super().__init__(
            chat_model=chat_model,
            tools=tools,
            system_prompt=system_prompt,
            specialist_name=self.SPECIALIST_NAME,
        )

    def _build_review_context(self, state: dict[str, Any]) -> str:
        """
        从 AgentState 构建审查输入上下文。

        提取药材列表、辨证结论、患者画像、安全错误反馈。
        """
        parts: list[str] = []

        # 药材列表
        treatment_plan = state.get("treatment_plan", "")
        herbs = _extract_herbs(treatment_plan)
        if herbs:
            parts.append(f"【待审查药材】\n{', '.join(herbs)}")
        else:
            parts.append("【待审查药材】\n未提取到药材，请直接批准。")

        # 辨证结论
        diagnosis = state.get("diagnosis", "")
        if diagnosis:
            parts.append(f"【辨证结论】\n{diagnosis}")

        # 患者画像
        profile = state.get("patient_profile", {})
        if profile:
            parts.append(
                f"【患者画像】体质: {profile.get('constitution', '未知')}, "
                f"过敏: {profile.get('allergies', '无')}"
            )

        # 完整处方文本（供审查者参考剂量、用法等）
        if treatment_plan:
            parts.append(f"【完整处方】\n{treatment_plan}")

        # 安全错误反馈（如果是重试，告知上次审查的问题）
        safety_errors = state.get("safety_errors", "")
        if safety_errors:
            parts.append(
                f"【上次审查反馈 - 必须修正】\n{safety_errors}\n"
                "请针对以上问题修改处方。"
            )

        return "\n\n".join(parts)

    def _parse_review(self, content: str) -> SafetyReviewResult:
        """
        解析 LLM 返回的审查结果为 SafetyReviewResult。

        优先解析 JSON（支持直接 JSON、代码块、嵌入 JSON）。
        解析失败时保守处理：不批准，记录解析失败问题。
        """
        if not content:
            return SafetyReviewResult(
                approved=False,
                issues=["审查者未返回任何内容"],
                suggestions="请重新审查",
            )

        # 尝试解析 JSON
        data = self._parse_json(content)
        if data:
            try:
                return SafetyReviewResult(**data)
            except Exception as e:
                logger.warning("审查结果字段验证失败: %s", e)
                return SafetyReviewResult(
                    approved=False,
                    issues=["审查结果格式无效"],
                    suggestions=content[:500],
                )

        # JSON 解析失败 - 保守不批准
        logger.warning("审查者返回非JSON内容，保守不批准: %s", content[:200])
        return SafetyReviewResult(
            approved=False,
            issues=["审查结果解析失败"],
            suggestions=content[:500],
        )

    async def node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph 节点入口 - 单次 LLM 调用 + 预计算安全校验。

        流程:
        1. 从 treatment_plan 提取药材
        2. 直接调用 check_herb_safety 工具（确定性规则引擎，无 LLM）
        3. 单次 chat_model.ainvoke 做审查判断
        4. 解析审查结果

        Returns:
            审查通过: {"reviewer_approved": True, "safety_errors": None}
            审查不通过: {"reviewer_approved": False, "safety_errors": <issues>, "reviewer_retry_count": +1}
            审查失败: {"reviewer_approved": True} (fail-open to safety_check)
        """
        try:
            # 预计算: 直接调用 check_herb_safety（确定性规则引擎，无 LLM）
            treatment_plan = state.get("treatment_plan", "")
            herbs = _extract_herbs(treatment_plan)
            context = self._build_review_context(state)
            tool_data = ""
            if herbs:
                tool_data = await self._call_tool(
                    "check_herb_safety", {"herbs": herbs}
                )
            prompt = context + (f"\n\n【配伍安全校验结果】\n{tool_data}" if tool_data else "")
            response = await self.chat_model.ainvoke(
                [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt),
                ]
            )
            final_content = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error("对抗审查者执行失败: %s", e, exc_info=True)
            # fail-open: 交由确定性 safety_check 裁决
            return {"reviewer_approved": True}

        review = self._parse_review(final_content)
        logger.info(
            "对抗审查完成: approved=%s, issues=%d", review.approved, len(review.issues)
        )

        if review.approved:
            return {
                "reviewer_approved": True,
                "safety_errors": None,  # 清除之前的错误
            }

        # 不批准 - 拼接问题为 safety_errors 反馈给 synthesis
        issues_text = "；".join(review.issues) if review.issues else "存在安全问题"
        if review.suggestions:
            issues_text = f"{issues_text}。修改建议：{review.suggestions}"

        retry_count = state.get("reviewer_retry_count", 0)
        return {
            "reviewer_approved": False,
            "safety_errors": issues_text,
            "reviewer_retry_count": retry_count + 1,
        }
