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
import re
from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)

# 默认追问上限：达到此次数后强制进入诊断
DEFAULT_MAX_FOLLOWUPS = 2

# 感谢词（检测到时降级为 chat，不触发辨证）
_GRATITUDE_WORDS = {"谢谢", "感谢", "多谢", "thanks", "thank you"}


def _extract_herbs_from_treatment(text: str) -> list[str]:
    """从治疗计划文本中提取 herb_names 药材列表（供问诊判断当前处方组成）。"""
    if not text:
        return []
    m = re.search(r'"herb_names"\s*:\s*\[([^\]]*)\]', text)
    if m:
        return [h.strip().strip('"').strip("'") for h in m.group(1).split(",") if h.strip()]
    return []


def _detect_new_allergy_items(text: str) -> list[str]:
    """检测用户新报告的过敏原（"对X过敏"，非否定式移除），返回规范化过敏原列表。

    仅做数据传播（注入 patient_profile 供 specialists 即时可见），不做路由决策。
    否定式（"不过敏"/"不再...过敏"）属移除语义，返回空。
    """
    if not text or re.search(r"不过敏|不再.{0,4}过敏|过敏.{0,6}(好了|缓解|消失|没了)", text):
        return []
    token = r"[一-鿿A-Za-z0-9]{2,6}"  # 2+ 字符，避免误捕单字"不"
    items: list[str] = []
    for m in re.finditer(rf"对({token})过敏", text):
        raw = m.group(1)
        if raw and "不" not in raw and raw not in ("我", "现在", "之前", "的"):
            items.append(raw)
    return list(dict.fromkeys(items))


class InquiryResult(BaseModel):
    """问诊结构化输出（由 with_structured_output 强制 LLM 返回）。"""

    intent_type: str = Field(
        description="用户意图: chat(闲聊/问候/道谢/与当前处方无关的声明) / consult(知识咨询或需追问) / diagnose(具体病症求医，或需重新辨证/调整既有处方--如对当前处方药材过敏、新症状、药效反馈、要求换药)"
    )
    is_complete: bool = Field(default=False, description="当前信息是否足够进行辨证")
    symptoms: list[str] = Field(default_factory=list, description="从对话中提取的结构化症状")
    response: str = Field(
        default="",
        description="对用户的回复：chat=闲聊回应, consult=追问, diagnose=留空（不输出内容，理法方药由后续节点产出）",
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

        # 已开过处方时，注入当前药材清单与辨证，供 LLM 判断是否需要调整处方
        if state.get("has_provided_treatment"):
            herbs = _extract_herbs_from_treatment(state.get("treatment_plan", ""))
            if herbs:
                context_parts.append(f"当前处方药材: {', '.join(herbs)}")
            diagnosis = state.get("diagnosis", "")
            if diagnosis:
                context_parts.append(f"当前辨证: {diagnosis[:200]}")
            context_parts.append(
                "【已开过处方】若用户消息涉及对上述药材过敏、药效不佳、不良反应或要求调整，"
                "需重新开方则 intent=diagnose；与处方无关的声明（如对不在处方中的物质过敏、"
                "或「我对X不过敏了」这类移除过敏）则 intent=chat。"
            )

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
            "symptoms": list(existing_symptoms),
            "intent_type": intent_type,
        }
        # 只在 chat/consult 时向用户展示回复（追问/闲聊回应）。
        # diagnose 时不添加消息--理法方药由后续 specialists + synthesis 生成，
        # 避免追问/过渡语与诊断结论同时出现。
        if intent_type in ("chat", "consult"):
            out["messages"] = [{"role": "assistant", "content": result.response or ""}]
        # 只在生成追问（将展示给用户）时才递增计数
        if intent_type == "consult":
            out["inquiry_count"] = current_count + 1

        # 确定性数据传播：用户新报告的过敏原即时注入 patient_profile，
        # 使 specialists/synthesis 在本回合即可规避（MemRecall 在问诊前已加载旧画像）
        new_allergens = _detect_new_allergy_items(_last_user_message(state))
        if new_allergens:
            profile = dict(state.get("patient_profile") or {})
            cur = profile.get("allergies", "无")
            cur_items = [
                a.strip() for a in re.split(r"[、，,；;]", cur)
                if a.strip() and a.strip() not in ("无", "未知")
            ]
            for a in new_allergens:
                if a not in cur_items:
                    cur_items.append(a)
            profile["allergies"] = "、".join(cur_items) if cur_items else "无"
            out["patient_profile"] = profile
            logger.info("问诊注入新过敏原: %s -> %s", new_allergens, profile["allergies"])
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
