"""
问诊技能 - 意图识别与症状提取。

核心职责:
1. 识别用户意图（chat / consult / diagnose）
2. 从对话中提取结构化症状列表
3. 控制追问轮数：达到上限后强制进入辨证，避免生成追问后被路由丢弃

实现要点:
- 用 LangChain `with_structured_output(InquiryResult)` 强制 LLM 返回结构化数据，
  从根上避免手写 JSON 解析失败导致 intent 被静默改写（原 bug：解析失败回退 chat，
  使 diagnose 意图无法进入理法方药流程）。
- 结构化输出不可用或失败时回退 JSON 解析，并降级为 consult（继续问诊）而非 chat（直接结束）。
- diagnose 意图的 response 只输出简短过渡语，不输出医疗建议——理法方药交给 diagnosis/treatment。
"""

import logging
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)

# 默认追问上限：达到此次数后强制进入诊断
DEFAULT_MAX_FOLLOWUPS = 2

# 感谢词（检测到时降级为 chat，不触发辨证）
_GRATITUDE_WORDS = {"谢谢", "感谢", "多谢", "thanks", "thank you"}


class InquiryResult(BaseModel):
    """问诊结构化输出（由 with_structured_output 强制 LLM 返回）。"""

    intent_type: str = Field(
        description="用户意图: chat(闲聊/问候/道谢) / consult(知识咨询或需追问) / diagnose(具体病症求医)"
    )
    is_complete: bool = Field(default=False, description="当前信息是否足够进行辨证")
    symptoms: list[str] = Field(default_factory=list, description="从对话中提取的结构化症状")
    response: str = Field(
        default="",
        description="对用户的回复：chat=闲聊回应, consult=追问, diagnose=简短过渡语（禁止输出医疗建议/方药）",
    )


def _last_user_message(state: dict[str, Any]) -> str:
    """取 state 中最后一条用户消息内容。"""
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "type", "") in ("human", "user"):
            return getattr(msg, "content", "")
    return ""


class InquirySkill(BaseSkill):
    """
    问诊技能节点。

    负责多轮问诊交互，逐步收集患者的症状信息。
    当信息足够时，将 intent_type 设为 "diagnose" 以触发后续辨证流程。
    """

    def __init__(
        self,
        llm: Any = None,
        max_history: int = 5,
        max_followups: int = DEFAULT_MAX_FOLLOWUPS,
    ):
        """
        初始化问诊技能。

        Args:
            llm: LLM 实例
            max_history: 携带的历史对话轮次
            max_followups: 最大追问轮数（达到后强制诊断）
        """
        super().__init__(llm=llm)
        self.max_history = max_history
        self.max_followups = max_followups

    def build_messages(self, state: dict[str, Any]) -> list[BaseMessage]:
        """构建问诊消息列表，注入症状、文件内容、历史摘要等上下文。"""
        context_parts: list[str] = []

        symptoms = state.get("symptoms", [])
        if symptoms:
            context_parts.append(f"已收集的症状: {', '.join(symptoms)}")

        file_content = state.get("extracted_file_content", "")
        if file_content:
            context_parts.append(f"患者上传的文件内容:\n{file_content[:2000]}")

        summary = state.get("summary", "")
        if summary:
            context_parts.append(f"历史摘要: {summary}")

        messages = self._build_system_messages(self.system_prompt, context_parts)
        messages.extend(self._history_to_messages(state.get("messages", []), self.max_history))
        return messages

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        执行问诊逻辑。

        Returns:
            更新后的 messages, symptoms, intent_type（必要时递增 inquiry_count）
        """
        if not self.llm:
            return {"intent_type": "chat"}

        current_count = state.get("inquiry_count", 0)
        # 仅在初始诊断阶段（尚未提供治疗）应用追问上限，避免无限追问；
        # 已提供治疗后，用户的调整请求（如"对xx过敏"、"换一味药"）需正常分类并
        # 提取新信息后重新进入 diagnosis/treatment 出调整方，不能被上限跳过。
        if not state.get("has_provided_treatment") and current_count >= self.max_followups:
            logger.info("已追问 %d 次达上限，强制进入诊断", current_count)
            return {"intent_type": "diagnose"}

        # 调用 LLM（优先结构化输出）
        messages = self.build_messages(state)
        try:
            result = await self._invoke_structured(messages)
        except Exception as e:
            logger.error("问诊 LLM 调用失败: %s", e)
            return {
                "intent_type": "consult",
                "messages": [{"role": "assistant", "content": "抱歉，系统暂时无法响应，请稍后再试。"}],
            }

        intent_type = result.intent_type

        # 合并症状
        existing_symptoms = set(state.get("symptoms", []))
        existing_symptoms.update(result.symptoms or [])

        # 感谢词检测 - 用户只是道谢时降级为 chat，不触发辨证
        if any(word in _last_user_message(state) for word in _GRATITUDE_WORDS):
            intent_type = "chat"

        out = {
            "messages": [{"role": "assistant", "content": result.response or ""}],
            "symptoms": list(existing_symptoms),
            "intent_type": intent_type,
        }
        # 只在生成追问（将展示给用户）时才递增计数
        if intent_type == "consult":
            out["inquiry_count"] = current_count + 1
        return out

    async def _invoke_structured(self, messages: list[BaseMessage]) -> InquiryResult:
        """
        优先用结构化输出；不支持或失败时回退 JSON 解析。

        回退时降级为 consult（继续问诊）而非 chat（直接结束），避免误吞 diagnose 意图。
        """
        try:
            structured = self.llm.with_structured_output(InquiryResult)
            return await structured.ainvoke(messages)
        except NotImplementedError as e:
            logger.warning("LLM 不支持结构化输出，回退 JSON 解析: %s", e)
        except Exception as e:
            logger.warning("结构化输出调用失败，回退 JSON 解析: %s", e)

        response = await self.llm.ainvoke(messages)
        return self._parse_inquiry_json(response)

    def _parse_inquiry_json(self, response: str) -> InquiryResult:
        """JSON 回退解析；失败时降级为 consult（继续问诊）而非 chat（直接结束）。"""
        parsed = self.parse_json_response(response, fallback=None)
        if not parsed:
            logger.warning("问诊 JSON 解析失败，降级为 consult；原始响应: %s", (response or "")[:200])
            return InquiryResult(
                intent_type="consult",
                symptoms=[],
                response="抱歉，我没完全理解，能再描述一下具体的不适吗？",
            )
        return InquiryResult(
            intent_type=parsed.get("intent_type", "consult"),
            symptoms=parsed.get("symptoms", []),
            response=parsed.get("response", ""),
        )
