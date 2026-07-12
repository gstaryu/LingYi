"""
技能基类 — 统一的 Skill 加载与执行框架。

设计原则:
- 自动读取同目录同名 .md 文件作为 system prompt
- 提供 build_messages() 模板方法，子类可覆盖
- 子类只需实现 execute() 抽象方法
- 通过 node() 方法包装为 LangGraph 节点函数
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """
    技能基类。

    所有技能节点（Inquiry、Diagnosis、Treatment 等）都继承此类。
    子类只需:
    1. 实现 execute(state) -> dict 方法
    2. 在同目录放置同名 .md 文件作为 system prompt
    """

    def __init__(self, llm: Any = None):
        """
        初始化技能。

        Args:
            llm: LLM 实例（BaseLLM），用于生成回复
        """
        self.llm = llm
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """
        自动加载同目录同名 .md 文件作为 system prompt。

        例如: inquiry.py 会自动加载 inquiry.md
        如果 .md 文件不存在，返回空字符串并记录警告。
        """
        # 所有 skill 文件都在同一目录（lingyi/agent/skills/）
        skill_dir = Path(__file__).parent

        # 构造 .md 文件路径（类名去掉 Skill 后缀，转 snake_case）
        import re
        class_name = self.__class__.__name__
        # 去掉常见后缀
        for suffix in ("Skill", "Node"):
            if class_name.endswith(suffix):
                class_name = class_name[: -len(suffix)]
                break
        # CamelCase -> snake_case（处理连续大写字母如 RAG -> rag）
        # 在小写→大写、连续大写→大写+小写 的边界插入下划线
        class_name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", class_name)
        class_name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", class_name).lower()

        md_path = skill_dir / f"{class_name}.md"

        if md_path.exists():
            content = md_path.read_text(encoding="utf-8").strip()
            logger.debug("加载 prompt: %s (%d 字符)", md_path.name, len(content))
            return content

        logger.warning("未找到 prompt 文件: %s", md_path)
        return ""

    def build_messages(self, state: dict[str, Any]) -> list[BaseMessage]:
        """
        构建 LLM 调用的消息列表（模板方法）。

        默认实现: system prompt + 全部对话历史，返回 LangChain BaseMessage 列表。
        子类可覆盖以注入额外上下文（如症状、RAG 文档等），推荐复用
        _build_system_messages() 与 _history_to_messages() 两个助手以消除重复。

        Args:
            state: AgentState 字典

        Returns:
            BaseMessage 列表（SystemMessage / HumanMessage / AIMessage）
        """
        messages: list[BaseMessage] = self._build_system_messages(self.system_prompt, [])
        messages.extend(self._history_to_messages(state.get("messages", [])))
        return messages

    @staticmethod
    def _build_system_messages(prompt: str, context_parts: list[str]) -> list[BaseMessage]:
        """
        构建 system 消息序列：主 prompt（若有）+ 上下文块（若有，合并为一条）。

        各 Skill 的 build_messages 共享此助手，避免重复构造 SystemMessage。
        """
        msgs: list[BaseMessage] = []
        if prompt:
            msgs.append(SystemMessage(content=prompt))
        if context_parts:
            msgs.append(SystemMessage(content="\n\n".join(context_parts)))
        return msgs

    @staticmethod
    def _history_to_messages(
        history: list, max_history: int | None = None
    ) -> list[BaseMessage]:
        """
        将对话历史转为 BaseMessage 列表，可选截取最近 N 轮（每轮 user+assistant 两条）。

        统一各 Skill 的历史角色映射逻辑（human->HumanMessage, ai->AIMessage），
        消除原先在 inquiry/diagnosis/treatment/safety_guard 中各写一份的重复代码。
        """
        if not history:
            return []
        msgs = history[-max_history * 2 :] if max_history else history
        result: list[BaseMessage] = []
        for msg in msgs:
            role = getattr(msg, "type", "user")
            content = getattr(msg, "content", "")
            if role in ("human", "user"):
                result.append(HumanMessage(content=content))
            elif role in ("ai", "assistant"):
                result.append(AIMessage(content=content))
        return result

    @abstractmethod
    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        执行技能逻辑（抽象方法）。

        Args:
            state: AgentState 字典

        Returns:
            状态更新字典，将被合并到 AgentState 中
        """

    @staticmethod
    def parse_json_response(text: str, fallback: Any = None) -> dict[str, Any]:
        """
        解析 LLM 返回的 JSON 响应（公共工具方法）。

        支持三种格式:
        1. 标准 JSON
        2. ```json ... ``` 包裹的 JSON
        3. 包含 { ... } 的文本

        Args:
            text: LLM 返回的文本
            fallback: 解析失败时的默认返回值

        Returns:
            解析后的字典，解析失败返回 fallback
        """
        if fallback is None:
            fallback = {}

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

        # 尝试从代码块中提取
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        # 尝试从文本中提取 JSON 对象
        json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        return fallback

    async def node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        LangGraph 节点入口 — 包装 execute()。

        此方法直接传给 StateGraph.add_node()。

        Args:
            state: AgentState 字典

        Returns:
            状态更新字典
        """
        try:
            return await self.execute(state)
        except Exception as e:
            logger.error("技能执行失败 [%s]: %s", self.__class__.__name__, e, exc_info=True)
            # 返回错误信息，不中断图执行
            return {"messages": [{"role": "assistant", "content": f"抱歉，处理过程中出现错误: {e}"}]}
