"""
记忆检索节点 - 从数据库加载患者画像到 AgentState。

属于"记忆"领域（与 checkpointer、summarizer 同模块），不依赖 LLM、不加载 prompt，
因此不继承 BaseSkill，仅提供统一的 node() 接口供 LangGraph 注册。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MemRecallSkill:
    """
    记忆检索节点 - 从 Storage 加载患者画像到 state。

    仅在以下情况从数据库加载:
    1. state 中没有画像（首轮对话）
    2. 画像被更新过（profile_updated=True，上一轮 ProfileWriter 写入了新画像）
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
        加载患者画像到 state（每轮重载）。

        每轮都从数据库重载：单行主键查询廉价，且保证 ProfileWriterSkill 后台写入的
        最终可见性（不再依赖 profile_updated 标记，避免"标记已重置但写入后完成"的缺口）。

        Args:
            state: AgentState

        Returns:
            patient_profile 字段
        """
        if not self.storage:
            return {"patient_profile": {}}

        patient_id = state.get("username") or state.get("thread_id", "default_user")
        try:
            profile = await self.storage.get_profile(patient_id)
            logger.debug("画像加载成功: %s", patient_id)
            return {
                "patient_profile": {
                    "constitution": profile.constitution,
                    "allergies": profile.allergies,
                    "past_history": profile.past_history,
                }
            }
        except Exception as e:
            logger.warning("画像加载失败: %s", e)
            return {"patient_profile": {}}
