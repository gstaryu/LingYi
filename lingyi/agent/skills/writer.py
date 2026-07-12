"""
档案写入技能 — 会话结束时将诊疗信息持久化到患者画像。

在 LangGraph 图中作为最后一个节点执行，负责:
1. 从对话历史中提取体质、过敏史等关键信息
2. 合并到已有患者画像
3. 持久化存储到数据库

同时提供 mem_recall_node() 用于在图开始时加载患者画像。
"""

import json
import logging
import re
from typing import Any

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class WriterSkill(BaseSkill):
    """
    档案写入技能节点。

    使用 LLM 从对话历史中提取体质和过敏史信息，
    然后通过 Storage 接口持久化到数据库。
    """

    def __init__(self, llm: Any = None, storage: Any = None):
        """
        初始化档案写入技能。

        Args:
            llm: LLM 实例，用于提取画像信息
            storage: BaseProfileStore 实例，用于持久化
        """
        super().__init__(llm=llm)
        self.storage = storage

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        从对话中提取画像信息并持久化。

        Args:
            state: AgentState

        Returns:
            空字典（写入操作不影响图流转）
        """
        if not self.llm or not self.storage:
            return {}

        messages = state.get("messages", [])
        if not messages:
            return {}

        # 复制消息列表，防止异步任务访问被修改的引用
        messages_snapshot = list(messages)
        patient_id = state.get("thread_id", "default_user")

        # 异步执行画像提取，不阻塞响应返回
        import asyncio

        def _on_done(task: asyncio.Task):
            """回调：记录异步任务的异常（不阻塞主流程）。"""
            if task.cancelled():
                return
            exc = task.exception()
            if exc:
                logger.warning("画像异步提取/写入失败: %s", exc)

        task = asyncio.create_task(
            self._extract_and_save(patient_id, messages_snapshot)
        )
        task.add_done_callback(_on_done)

        # 标记画像正在更新，下一轮 mem_recall 会重新加载
        return {"profile_updated": True}

    def _build_extract_prompt(self, messages: list) -> list[dict[str, str]]:
        """构建画像提取 prompt。"""
        # 取最近 6 条消息用于提取
        recent_msgs = messages[-6:]
        conversation = "\n".join(
            f"{getattr(m, 'type', 'user')}: {getattr(m, 'content', '')}"
            for m in recent_msgs
        )

        return [
            {
                "role": "system",
                "content": (
                    "你是一个医疗信息提取助手。从以下对话中提取患者的关键信息。\n"
                    "请以 JSON 格式输出：\n"
                    '{"constitution": "体质类型", "allergies": "过敏史", "new_record": "本次诊疗摘要"}\n'
                    "如果某项信息未提及，使用默认值（体质: 未知, 过敏: 无, 摘要: 空字符串）。"
                ),
            },
            {"role": "user", "content": f"对话内容：\n{conversation}"},
        ]

    def _parse_profile(self, response: str) -> dict[str, str]:
        """解析 LLM 返回的画像 JSON。"""
        try:
            json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    k: v
                    for k, v in data.items()
                    if k in ("constitution", "allergies", "new_record") and v
                }
        except (json.JSONDecodeError, AttributeError):
            pass
        return {}

    async def _extract_and_save(self, patient_id: str, messages: list):
        """异步提取画像信息并持久化（不阻塞主流程）。"""
        try:
            extract_prompt = self._build_extract_prompt(messages)
            response = await self.llm.ainvoke(extract_prompt)
            profile_data = self._parse_profile(response)

            if profile_data:
                await self.storage.update_profile(patient_id, profile_data)
                logger.info("画像已更新: patient_id=%s", patient_id)
        except Exception as e:
            logger.warning("画像异步提取/写入失败: %s", e)


class MemRecallSkill:
    """
    记忆检索节点 — 从数据库加载患者画像到 state。

    不依赖 LLM，直接从 Storage 读取。
    """

    def __init__(self, storage: Any = None):
        """
        初始化记忆检索节点。

        Args:
            storage: BaseProfileStore 实例
        """
        self.storage = storage

    async def node(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        加载患者画像到 state。

        仅在以下情况从数据库加载:
        1. state 中没有画像（首轮对话）
        2. 画像被更新过（profile_updated=True）

        Args:
            state: AgentState

        Returns:
            patient_profile 字段
        """
        if not self.storage:
            return {"patient_profile": {}}

        # 已有画像且未更新，跳过加载
        existing = state.get("patient_profile", {})
        if existing and not state.get("profile_updated", False):
            logger.debug("画像已存在且未更新，跳过加载")
            return {}

        patient_id = state.get("thread_id", "default_user")
        try:
            profile = await self.storage.get_profile(patient_id)
            logger.info("画像加载成功: %s", patient_id)
            return {
                "patient_profile": {
                    "constitution": profile.constitution,
                    "allergies": profile.allergies,
                    "past_history": profile.past_history,
                },
                "profile_updated": False,  # 重置更新标记
            }
        except Exception as e:
            logger.warning("画像加载失败: %s", e)
            return {"patient_profile": {}}
