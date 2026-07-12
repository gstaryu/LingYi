"""
辨证技能 — 中医"理法方术调"推演。

根据收集的症状、患者画像、RAG 检索到的文献，执行辨证论治。
输出包含: 病机分析（理）、治则治法（法）。
"""

import logging
from typing import Any

from langchain_core.messages import BaseMessage

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class DiagnosisSkill(BaseSkill):
    """
    辨证技能节点。

    整合症状、患者画像、RAG 文献等信息，调用 LLM 进行辨证推理。
    """

    def __init__(self, llm: Any = None, max_history: int = 3):
        """
        初始化辨证技能。

        Args:
            llm: LLM 实例
            max_history: 携带的历史对话轮次
        """
        super().__init__(llm=llm)
        self.max_history = max_history

    def build_messages(self, state: dict[str, Any]) -> list[BaseMessage]:
        """构建辨证消息列表，注入症状、画像、RAG 文献等上下文。"""
        context_parts: list[str] = []

        # 患者画像
        profile = state.get("patient_profile", {})
        if profile:
            context_parts.append(
                f"患者画像:\n"
                f"  体质: {profile.get('constitution', '未知')}\n"
                f"  过敏史: {profile.get('allergies', '无')}\n"
                f"  既往史: {', '.join(profile.get('past_history', [])) or '无'}"
            )

        # 上传文件内容
        file_content = state.get("extracted_file_content", "")
        if file_content:
            context_parts.append(f"患者上传的文件内容:\n{file_content[:2000]}")

        # 症状列表
        symptoms = state.get("symptoms", [])
        if symptoms:
            context_parts.append(f"已确认的症状: {', '.join(symptoms)}")

        # RAG 检索到的文献
        retrieved_docs = state.get("retrieved_docs", [])
        if retrieved_docs:
            docs_text = "\n---\n".join(retrieved_docs[:5])
            context_parts.append(f"相关经典文献参考:\n{docs_text}")

        # 历史摘要
        summary = state.get("summary", "")
        if summary:
            context_parts.append(f"病历摘要: {summary}")

        messages = self._build_system_messages(self.system_prompt, context_parts)
        messages.extend(self._history_to_messages(state.get("messages", []), self.max_history))
        return messages

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        执行辨证推理。

        Args:
            state: AgentState

        Returns:
            更新后的 messages 和 diagnosis
        """
        if not self.llm:
            return {"diagnosis": "无法执行辨证：LLM 未配置"}

        messages = self.build_messages(state)
        try:
            response = await self.llm.ainvoke(messages)
        except Exception as e:
            logger.error("辨证 LLM 调用失败: %s", e)
            return {"diagnosis": f"辨证失败: {e}"}

        return {
            "messages": [{"role": "assistant", "content": response}],
            "diagnosis": response,
        }
