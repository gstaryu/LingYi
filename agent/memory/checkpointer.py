import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

# 定义数据库存储路径
DB_PATH = "storage/checkpoints.db"


def get_checkpointer():
    """
    创建一个基于 SQLite 的 LangGraph 持久化器。
    它允许通过 thread_id 找回对话状态。
    """
    # 确保存储目录存在
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # 连接数据库 (check_same_thread=False 允许在多线程环境下使用，如 Streamlit)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return SqliteSaver(conn)


# 导出实例
memory_saver = get_checkpointer()