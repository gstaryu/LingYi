"""
多智能体专家基类 - 单次 LLM 调用 + 预取工具数据。

设计要点:
- 每个专家在 node() 中做 **恰好一次** chat_model.ainvoke（不再用 ReAct create_agent 循环）
- 子类可覆写 prefetch()，在 LLM 调用前 **直接** 调用工具（不经过 LLM），将结果拼入 prompt
- 节点返回 {"consultation_notes": [note]}，不修改 messages（避免并行 reducer 冲突）
- JSON 解析带 fallback，保证结构稳定
- 依赖注入: chat_model 通过构造函数注入，生产用 ChatOpenAI，测试用 StubChatModel
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class SpecialistBase:
    """
    专家 Agent 基类 - 单次 LLM 调用架构。

    子类只需定义 SYSTEM_PROMPT、SPECIALIST_NAME，并实现 _parse_note()。
    可选覆写 prefetch() 在 LLM 调用前预取工具数据。

    依赖注入: chat_model 通过构造函数注入，生产用 ChatOpenAI，测试用 StubChatModel。
    """

    SYSTEM_PROMPT: str = ""
    SPECIALIST_NAME: str = ""

    def __init__(
        self,
        chat_model: Any,
        tools: list | None = None,
        system_prompt: str | None = None,
        specialist_name: str | None = None,
    ):
        """
        初始化专家 Agent。

        Args:
            chat_model: ChatOpenAI 实例（或 BaseChatModel，支持 ainvoke）
            tools: 该专家可用的工具子集（仅供 prefetch 直接调用，不绑定给 LLM）
            system_prompt: 专家系统提示词（默认用子类 SYSTEM_PROMPT）
            specialist_name: 专家名称（默认用子类 SPECIALIST_NAME）
        """
        self.chat_model = chat_model
        self.tools = tools or []
        self.system_prompt = system_prompt or self.SYSTEM_PROMPT
        self.specialist_name = specialist_name or self.SPECIALIST_NAME

    # ==================== 工具预取 ====================

    async def prefetch(self, state: dict[str, Any]) -> str:
        """
        在 LLM 调用前 **直接** 调用工具获取数据（不经过 LLM 推理）。

        子类可覆写：用 _call_tool() 直接调用领域工具，返回数据文本。
        默认返回空字符串（即不做预取，仅靠症状+画像做 1 次 LLM 调用）。

        Returns:
            预取的数据文本，将拼接到 prompt 末尾。空字符串表示无预取数据。
        """
        return ""

    async def _call_tool(self, name: str, args: dict) -> str:
        """
        按名称直接调用工具（异步），返回结果的字符串表示。

        工具不存在或调用失败时返回空字符串，不中断专家流程。

        Args:
            name: 工具名称（如 "search_tcm_classics"）
            args: 工具参数字典（如 {"query": "..."} ）

        Returns:
            工具返回值的 str() 形式；工具不存在或失败时返回 ""
        """
        for t in self.tools:
            if t.name == name:
                try:
                    result = await t.ainvoke(args)
                    return str(result)
                except Exception as e:  # noqa: BLE001 - 工具失败不应中断专家
                    logger.warning("专家 %s 工具 %s 调用失败: %s", self.specialist_name, name, e)
                    return ""
        return ""

    # ==================== 上下文构建 ====================

    def _build_context(self, state: dict[str, Any]) -> str:
        """
        从 AgentState 构建专家输入上下文。

        提取症状、患者画像、最近对话、已有辨证结果等信息。
        """
        parts: list[str] = []

        symptoms = state.get("symptoms", [])
        if symptoms:
            parts.append(f"【患者症状】\n{', '.join(symptoms)}")

        profile = state.get("patient_profile", {})
        if profile:
            parts.append(
                f"【患者画像】体质: {profile.get('constitution', '未知')}, "
                f"过敏: {profile.get('allergies', '无')}"
            )

        # 最近的对话上下文（取最近 6 条消息中的用户主诉）
        messages = state.get("messages", [])
        for msg in messages[-6:]:
            role = getattr(msg, "type", "")
            content = getattr(msg, "content", "")
            if role in ("human", "user") and content:
                parts.append(f"【患者主诉】{content[:500]}")

        # 已有的辨证结果（方剂和本草专家可能需要参考）
        diagnosis = state.get("diagnosis", "")
        if diagnosis:
            parts.append(f"【辨证结果】{diagnosis}")

        # 文件解析内容
        file_content = state.get("extracted_file_content", "")
        if file_content:
            parts.append(f"【文件内容】{file_content[:1000]}")

        return "\n\n".join(parts) if parts else "请根据可用信息进行会诊分析。"

    # ==================== JSON 解析 ====================

    @staticmethod
    def _parse_json(content: str) -> dict | None:
        """
        解析 LLM 返回的 JSON（支持直接 JSON、代码块、嵌入 JSON）。

        与 BaseSkill.parse_json_response 逻辑一致，但独立实现避免循环依赖。
        """
        if not content:
            return None
        # 直接解析
        try:
            result = json.loads(content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass
        # 代码块提取
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass
        # 嵌入 JSON 提取（非贪婪匹配最外层大括号）
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    # ==================== 节点入口 ====================

    async def node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph 节点入口 - 单次 LLM 调用 + 预取工具数据。

        流程:
        1. _build_context(state) 构建上下文
        2. prefetch(state) 直接调用工具获取数据（不经 LLM）
        3. chat_model.ainvoke([SystemMessage, HumanMessage]) 做恰好 1 次 LLM 调用
        4. _parse_note() 解析为会诊笔记

        Returns:
            {"consultation_notes": [note]} - 不修改 messages，避免并行 reducer 冲突
        """
        try:
            context = self._build_context(state)
            tool_data = await self.prefetch(state)
            prompt = context + (f"\n\n【工具数据】\n{tool_data}" if tool_data else "")
            response = await self.chat_model.ainvoke(
                [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt),
                ]
            )
            final_content = response.content if hasattr(response, "content") else str(response)
        except Exception as e:  # noqa: BLE001 - 专家失败不应中断图
            logger.error("专家 %s 执行失败: %s", self.specialist_name, e, exc_info=True)
            final_content = ""

        note = self._parse_note(final_content)
        logger.info("专家 %s 完成会诊笔记", self.specialist_name)
        return {"consultation_notes": [note]}

    def _parse_note(self, content: str) -> dict[str, Any]:
        """解析最终 AI 消息为会诊笔记字典。子类必须实现。"""
        raise NotImplementedError
