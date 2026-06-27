"""
LangGraph 会话检查点 — 基于 SQLite 的状态持久化。

使用 langgraph-checkpoint-sqlite 的 AsyncSqliteSaver，
支持异步读写会话状态，实现对话中断后自动恢复。
"""

import logging
import os

logger = logging.getLogger(__name__)


def create_checkpointer(db_path: str):
    """
    创建 LangGraph 异步 SQLite 检查点。

    AsyncSqliteSaver 需要一个 aiosqlite.Connection 实例。
    注意: from_conn_string() 返回 async context manager，不能直接传给 compile()。

    Args:
        db_path: SQLite 数据库文件路径（通常为 storage/checkpoints.db）

    Returns:
        AsyncSqliteSaver 实例，可直接传给 StateGraph.compile(checkpointer=...)
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    # 确保目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    logger.info("创建 LangGraph 检查点: %s", db_path)
    # 创建 aiosqlite 连接并传给 AsyncSqliteSaver 构造函数
    # 连接会在首次使用时懒启动
    conn = aiosqlite.connect(db_path)
    return AsyncSqliteSaver(conn)
