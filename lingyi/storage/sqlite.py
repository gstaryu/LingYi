"""
SQLite 存储实现 - 用户、画像、线程管理的异步 SQLite 实现。

设计原则:
- 使用 aiosqlite 实现全异步操作
- 密码哈希使用 bcrypt（比 SHA-256 更安全）
- 连接/事务逻辑集中在 SQLiteBase，单一 SQLiteStorage 实现三个 ABC，共享一个连接
- 所有异常统一抛出 StorageError

注: 不再拆分为 SQLiteUserStore/SQLiteProfileStore/SQLiteThreadStore 三个独立类--
它们共享同一 DB 文件与连接，拆分反而引入了"仅靠多继承 MRO 才能用 _transaction"的脆弱耦合。
单一 SQLiteStorage 高内聚地承载同一数据库的全部 CRUD，接口契约仍由 Base*Store ABC 保障。
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
import bcrypt

from lingyi.exceptions import StorageError
from lingyi.storage.base import (
    BaseProfileStore,
    BaseThreadStore,
    BaseUserStore,
    ThreadInfo,
    UserProfile,
)

logger = logging.getLogger(__name__)

# ==================== 建表 SQL ====================
_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_PROFILES_TABLE = """
CREATE TABLE IF NOT EXISTS profiles (
    patient_id TEXT PRIMARY KEY,
    constitution TEXT DEFAULT '未知',
    allergies TEXT DEFAULT '无',
    past_history TEXT DEFAULT '[]',
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    title TEXT DEFAULT '新对话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class SQLiteBase:
    """
    SQLite 连接与事务管理公共基类。

    持有单一持久连接（懒初始化、复用），提供事务上下文与关闭方法。
    所有存储实现共享此基类，避免连接管理代码重复。
    """

    def __init__(self, db_path: str):
        """
        初始化存储。

        Args:
            db_path: SQLite 数据库文件路径
        """
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None  # 持久连接，懒初始化
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        logger.info("SQLiteBase 初始化: db_path=%s", db_path)

    async def _get_conn(self) -> aiosqlite.Connection:
        """获取持久数据库连接（懒初始化，复用同一连接）。"""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            logger.debug("SQLite 持久连接已创建: %s", self._db_path)
        return self._conn

    @asynccontextmanager
    async def _transaction(self):
        """获取数据库事务（上下文管理器，自动提交/回滚）。"""
        conn = await self._get_conn()
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    async def close(self) -> None:
        """关闭持久连接。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.debug("SQLite 持久连接已关闭")


class SQLiteStorage(SQLiteBase, BaseUserStore, BaseProfileStore, BaseThreadStore):
    """
    统一 SQLite 存储 - 实现用户、画像、线程三套接口，共享同一个数据库连接。

    通过 SQLiteBase 复用连接/事务逻辑；通过三个 Base*Store ABC 保障接口契约。
    """

    def __init__(self, db_path: str):
        super().__init__(db_path)
        logger.info("SQLiteStorage 初始化完成: %s", db_path)

    # ==================== 建表 ====================

    async def init_db(self) -> None:
        """初始化数据库表结构（幂等）。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(_CREATE_USERS_TABLE)
                await conn.execute(_CREATE_PROFILES_TABLE)
                await conn.execute(_CREATE_THREADS_TABLE)
            logger.info("数据库初始化完成: %s", self._db_path)
        except Exception as e:
            raise StorageError(f"数据库初始化失败: {e}") from e

    # ==================== 用户管理（BaseUserStore）====================

    async def create_user(self, username: str, password: str) -> bool:
        """创建新用户，密码使用 bcrypt 哈希存储。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT username FROM users WHERE username = ?", (username,)
                )
                if await cursor.fetchone():
                    return False

                pwd_hash = bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8")

                await conn.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, pwd_hash),
                )
            logger.info("用户创建成功: %s", username)
            return True
        except StorageError:
            raise
        except Exception as e:
            raise StorageError(f"用户创建失败: {e}") from e

    async def verify_user(self, username: str, password: str) -> bool:
        """验证用户密码（bcrypt 比对）。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT password FROM users WHERE username = ?", (username,)
                )
                row = await cursor.fetchone()
                if not row:
                    return False

                stored_hash = row["password"].encode("utf-8")
                return bcrypt.checkpw(password.encode("utf-8"), stored_hash)
        except Exception as e:
            raise StorageError(f"用户验证失败: {e}") from e

    # ==================== 画像管理（BaseProfileStore）====================

    async def get_profile(self, patient_id: str) -> UserProfile:
        """获取患者画像。不存在时返回默认画像。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM profiles WHERE patient_id = ?", (patient_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return UserProfile(
                        patient_id=patient_id,
                        constitution=row["constitution"] or "未知",
                        allergies=row["allergies"] or "无",
                        past_history=json.loads(row["past_history"]) if row["past_history"] else [],
                    )
        except Exception as e:
            logger.warning("读取画像失败: %s", e)

        return UserProfile(patient_id=patient_id)

    async def update_profile(self, patient_id: str, data: dict[str, Any]) -> None:
        """更新患者画像（upsert 语义）。new_record 追加到 past_history（最多 10 条）。"""
        try:
            current = await self.get_profile(patient_id)
            new_history = current.past_history.copy()

            if data.get("new_record"):
                new_history.append(data["new_record"])
                new_history = new_history[-10:]

            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO profiles (patient_id, constitution, allergies, past_history, last_update)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(patient_id) DO UPDATE SET
                        constitution = excluded.constitution,
                        allergies = excluded.allergies,
                        past_history = excluded.past_history,
                        last_update = CURRENT_TIMESTAMP
                    """,
                    (
                        patient_id,
                        data.get("constitution", current.constitution),
                        data.get("allergies", current.allergies),
                        json.dumps(new_history, ensure_ascii=False),
                    ),
                )
            logger.info("画像已更新: %s", patient_id)
        except Exception as e:
            raise StorageError(f"更新画像失败: {e}") from e

    async def list_profiles(self) -> list[dict[str, str]]:
        """列出所有患者画像（按最后更新时间降序）。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT patient_id, last_update FROM profiles ORDER BY last_update DESC"
                )
                rows = await cursor.fetchall()
                return [{"patient_id": r["patient_id"], "last_update": r["last_update"]} for r in rows]
        except Exception as e:
            logger.warning("获取画像列表失败: %s", e)
            return []

    # ==================== 线程管理（BaseThreadStore）====================

    async def add_thread(self, username: str, thread_id: str) -> None:
        """创建新会话线程。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT OR IGNORE INTO threads (thread_id, username) VALUES (?, ?)",
                    (thread_id, username),
                )
        except Exception as e:
            logger.warning("创建线程失败: %s", e)

    async def get_threads(self, username: str) -> list[ThreadInfo]:
        """获取用户的所有会话线程（按创建时间降序）。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT thread_id, title, created_at FROM threads WHERE username = ? ORDER BY created_at DESC",
                    (username,),
                )
                rows = await cursor.fetchall()
                return [
                    ThreadInfo(
                        thread_id=r["thread_id"],
                        username=username,
                        title=r["title"] or "新对话",
                        created_at=r["created_at"] or "",
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.warning("获取线程列表失败: %s", e)
            return []

    async def rename_thread(self, thread_id: str, new_title: str) -> None:
        """重命名会话线程。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    "UPDATE threads SET title = ? WHERE thread_id = ?",
                    (new_title, thread_id),
                )
        except Exception as e:
            raise StorageError(f"重命名线程失败: {e}") from e

    async def delete_thread(self, thread_id: str) -> None:
        """删除会话线程。"""
        try:
            async with self._transaction() as conn:
                await conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
        except Exception as e:
            logger.warning("删除线程失败: %s", e)
