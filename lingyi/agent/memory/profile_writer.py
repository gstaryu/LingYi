"""
画像写入节点 - 会话结束时将诊疗信息持久化到患者画像。

属于"记忆"领域。原 WriterSkill 改名为 ProfileWriterSkill 以反映真实职责
（持久化画像，而非生成回复），并与 MemRecallSkill 配对（recall 加载、writer 写入）。

设计: 画像提取是一次 LLM 调用，属诊疗结束后的副作用持久化，不应阻塞响应。
      execute 用 asyncio.create_task 在后台调度（fire-and-forget），立即返回；
      任务存入 _pending 集合防 GC，应用关闭时由 flush() 统一等待避免丢写。
      MemRecallSkill 改为每轮重载（DB 单行 PK 查询廉价），保证后台写入的最终可见性。
"""

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from lingyi.agent.skills.base import BaseSkill

logger = logging.getLogger(__name__)

# 画像提取超时（秒）- 超时则跳过本次写入，不阻塞响应过久
DEFAULT_EXTRACT_TIMEOUT = 15


class ProfileWriterSkill(BaseSkill):
    """
    画像写入技能节点。

    使用 LLM 从对话历史中提取体质和过敏史信息，
    然后通过 Storage 接口持久化到数据库。
    """

    def __init__(self, llm: Any = None, storage: Any = None, timeout: int = DEFAULT_EXTRACT_TIMEOUT):
        """
        初始化画像写入技能。

        Args:
            llm: LLM 实例，用于提取画像信息
            storage: BaseProfileStore 实例，用于持久化
            timeout: 单次画像提取超时（秒），超时则该任务取消
        """
        super().__init__(llm=llm)
        self.storage = storage
        self.timeout = timeout
        # 待完成的后台写入任务集合：防止任务被 GC，并在应用关闭时 flush
        self._pending: set[asyncio.Task] = set()

    async def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        调度后台画像提取与持久化（fire-and-forget，不阻塞响应）。

        画像提取是一次 LLM 调用，属于诊疗结束后的副作用持久化，不应让用户等待。
        因此用 create_task 在后台执行，execute 立即返回；任务存入 _pending 防 GC，
        并在应用关闭时由 flush() 统一等待，避免事件循环关闭导致丢写。

        Returns:
            {"profile_updated": True} 标记（MemRecallSkill 已改为每轮重载，此标记保留兼容）
        """
        if not self.llm or not self.storage:
            return {}

        messages = state.get("messages", [])
        if not messages:
            return {}

        # 复制消息列表，防止后台任务执行期间原引用被修改
        messages_snapshot = list(messages)
        patient_id = state.get("username") or state.get("thread_id", "default_user")

        # 后台执行提取+写库；用 timeout 包裹防止单任务无限挂起
        task = asyncio.create_task(
            self._run_with_timeout(patient_id, messages_snapshot)
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

        return {"profile_updated": True}

    async def _run_with_timeout(self, patient_id: str, messages: list) -> None:
        """带超时的画像提取+持久化（后台任务体）。"""
        try:
            await asyncio.wait_for(
                self._extract_and_save(patient_id, messages),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("画像提取超时（%ds），跳过本次写入: %s", self.timeout, patient_id)
        except Exception as e:
            logger.warning("画像提取/写入失败: %s", e)

    async def flush(self) -> None:
        """
        等待所有待完成的画像写入完成（应用关闭时调用，防止丢写）。

        快照待处理任务后统一 gather；新加入的任务不会被误清。
        """
        if not self._pending:
            return
        tasks = list(self._pending)
        logger.info("等待 %d 个画像写入任务完成...", len(tasks))
        await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.difference_update(tasks)
        logger.info("画像写入 flush 完成")

    def _build_extract_prompt(self, messages: list) -> list[BaseMessage]:
        """构建画像提取 prompt（取最近 6 条消息）。"""
        recent_msgs = messages[-6:]
        conversation = "\n".join(
            f"{getattr(m, 'type', 'user')}: {getattr(m, 'content', '')}"
            for m in recent_msgs
        )

        return [
            SystemMessage(
                content=(
                    "你是一个医疗信息提取助手。从以下对话中提取患者的关键信息。\n"
                    "请以 JSON 格式输出：\n"
                    '{"constitution": "体质类型", "allergies": "过敏史", "new_record": "本次诊疗摘要"}\n'
                    "如果某项信息未提及，使用默认值（体质: 未知, 过敏: 无, 摘要: 空字符串）。"
                )
            ),
            HumanMessage(content=f"对话内容：\n{conversation}"),
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

    async def _extract_and_save(self, patient_id: str, messages: list) -> None:
        """提取画像信息并持久化。"""
        extract_prompt = self._build_extract_prompt(messages)
        response = await self.llm.ainvoke(extract_prompt)
        profile_data = self._parse_profile(response)

        if profile_data:
            await self.storage.update_profile(patient_id, profile_data)
            logger.info("画像已更新: patient_id=%s", patient_id)
