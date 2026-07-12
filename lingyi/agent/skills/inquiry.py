"""
问诊技能 — 意图识别与症状提取。

核心职责:
1. 识别用户意图（chat / consult / diagnose）
2. 从对话中提取结构化症状列表
3. 判断是否已收集足够信息进入辨证阶段
"""

import logging
from typing import Any

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class InquirySkill(BaseSkill):
    """
    问诊技能节点。

    负责多轮问诊交互，逐步收集患者的症状信息。
    当信息足够时，将 intent_type 设为 "diagnose" 以触发后续辨证流程。
    """

    def __init__(self, llm: Any = None, max_history: int = 5):
        """
        初始化问诊技能。

        Args:
            llm: LLM 实例
            max_history: 携带的历史对话轮次
        """
        super().__init__(llm=llm)
        self.max_history = max_history

    def build_messages(self, state: dict[str, Any]) -> list[dict[str, str]]:
        """构建问诊消息列表，注入症状、文件内容等上下文。"""
        messages: list[dict[str, str]] = []

        # System prompt
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 注入上下文信息
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

        if context_parts:
            messages.append({
                "role": "system",
                "content": "\n\n".join(context_parts),
            })

        # 对话历史（截取最近 N 条）
        history = state.get("messages", [])
        recent = history[-self.max_history * 2:] if history else []
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
        执行问诊逻辑。

        Args:
            state: AgentState

        Returns:
            更新后的 messages, symptoms, intent_type
        """
        if not self.llm:
            return {"intent_type": "chat"}

        # 检查是否已完成治疗（后续跟进模式）
        if state.get("has_provided_treatment"):
            return await self._handle_followup(state)

        # 正常问诊流程
        messages = self.build_messages(state)
        try:
            response = await self.llm.ainvoke(messages)
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            return {"intent_type": "chat", "messages": [{"role": "assistant", "content": "抱歉，系统暂时无法响应，请稍后再试。"}]}

        # 解析 JSON 响应
        parsed = self.parse_json_response(response, fallback={"response": response, "intent_type": "chat", "symptoms": []})

        # 合并症状
        existing_symptoms = set(state.get("symptoms", []))
        new_symptoms = parsed.get("symptoms", [])
        existing_symptoms.update(new_symptoms)

        # 确定意图
        intent_type = parsed.get("intent_type", "chat")

        # 感谢词检测 — 如果用户只是说谢谢，不触发辨证
        gratitude_words = {"谢谢", "感谢", "多谢", "thanks", "thank you"}
        last_user_msg = ""
        for msg in reversed(state.get("messages", [])):
            if getattr(msg, "type", "") in ("human", "user"):
                last_user_msg = getattr(msg, "content", "")
                break
        if any(word in last_user_msg for word in gratitude_words):
            intent_type = "chat"

        result = {
            "messages": [{"role": "assistant", "content": parsed.get("response", response)}],
            "symptoms": list(existing_symptoms),
            "intent_type": intent_type,
        }
        # 只在需要追问时才递增计数
        if intent_type == "consult":
            result["inquiry_count"] = state.get("inquiry_count", 0) + 1
        return result

    async def _handle_followup(self, state: dict[str, Any]) -> dict[str, Any]:
        """处理治疗后的跟进对话。"""
        messages = self.build_messages(state)
        messages.append({
            "role": "system",
            "content": "患者已经收到了治疗方案，现在进行后续跟进。请根据患者的问题给予适当的回复。",
        })

        try:
            response = await self.llm.ainvoke(messages)
        except Exception as e:
            logger.error("跟进回复失败: %s", e)
            response = "抱歉，系统暂时无法响应。"

        return {
            "messages": [{"role": "assistant", "content": response}],
            "intent_type": "chat",
        }

