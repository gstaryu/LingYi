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
from lingyi.knowledge.models import Contraindication, Formula, FormulaComponent, Herb
from lingyi.storage.base import (
    BaseContraindicationStore,
    BaseFormulaStore,
    BaseHerbStore,
    BaseMemberStore,
    BaseProfileStore,
    BaseThreadStore,
    BaseUserStore,
    Member,
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
    constitution_history TEXT DEFAULT '[]',
    birth_year INTEGER,
    gender TEXT DEFAULT '',
    medical_history TEXT DEFAULT '[]',
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    title TEXT DEFAULT '新对话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    member_id TEXT DEFAULT ''
)
"""

_CREATE_MEMBERS_TABLE = """
CREATE TABLE IF NOT EXISTS members (
    member_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_HERBS_TABLE = """
CREATE TABLE IF NOT EXISTS herbs (
    name TEXT PRIMARY KEY,
    aliases TEXT DEFAULT '[]',
    nature_flavor TEXT DEFAULT '',
    meridians TEXT DEFAULT '[]',
    efficacy TEXT DEFAULT '',
    indications TEXT DEFAULT '[]',
    dosage TEXT DEFAULT '',
    processing TEXT DEFAULT '',
    contraindications TEXT DEFAULT ''
)
"""

_CREATE_FORMULAS_TABLE = """
CREATE TABLE IF NOT EXISTS formulas (
    name TEXT PRIMARY KEY,
    source TEXT DEFAULT '',
    composition TEXT DEFAULT '[]',
    indication TEXT DEFAULT '',
    modifications TEXT DEFAULT '',
    contraindications TEXT DEFAULT '',
    category TEXT DEFAULT ''
)
"""

_CREATE_CONTRAINDICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS contraindications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    herb TEXT NOT NULL,
    type TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    severity TEXT DEFAULT ''
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


class SQLiteStorage(
    SQLiteBase,
    BaseUserStore,
    BaseMemberStore,
    BaseProfileStore,
    BaseThreadStore,
    BaseHerbStore,
    BaseFormulaStore,
    BaseContraindicationStore,
):
    """
    统一 SQLite 存储 - 实现用户、画像、线程、知识库（本草/方剂/禁忌）接口，共享同一个数据库连接。

    通过 SQLiteBase 复用连接/事务逻辑；通过各 Base*Store ABC 保障接口契约。
    """

    def __init__(self, db_path: str):
        super().__init__(db_path)
        logger.info("SQLiteStorage 初始化完成: %s", db_path)

    # ==================== 建表 ====================

    async def init_db(self) -> None:
        """初始化数据库表结构（幂等；含列迁移）。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(_CREATE_USERS_TABLE)
                await conn.execute(_CREATE_PROFILES_TABLE)
                await conn.execute(_CREATE_THREADS_TABLE)
                await conn.execute(_CREATE_MEMBERS_TABLE)
                await conn.execute(_CREATE_HERBS_TABLE)
                await conn.execute(_CREATE_FORMULAS_TABLE)
                await conn.execute(_CREATE_CONTRAINDICATIONS_TABLE)
                # 迁移：旧库补列（幂等）
                await self._migrate_columns(
                    conn,
                    "profiles",
                    {
                        "constitution_history": "TEXT DEFAULT '[]'",
                        "birth_year": "INTEGER",
                        "gender": "TEXT DEFAULT ''",
                        "medical_history": "TEXT DEFAULT '[]'",
                    },
                )
                await self._migrate_columns(conn, "threads", {"member_id": "TEXT DEFAULT ''"})
                # 迁移：历史账号补主成员、历史会话归属主成员（幂等）
                await self._backfill_members(conn)
                # 禁忌表按 herb 建索引加速查询
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_contraindications_herb "
                    "ON contraindications(herb)"
                )
                # 唯一索引保证幂等（同 herb+type+detail+severity 不重复插入）
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_contra_unique "
                    "ON contraindications(herb, type, detail, severity)"
                )
            logger.info("数据库初始化完成: %s", self._db_path)
        except Exception as e:
            raise StorageError(f"数据库初始化失败: {e}") from e

    @staticmethod
    async def _migrate_columns(conn, table: str, columns: dict[str, str]) -> None:
        """幂等补列：缺列则 ALTER ADD（table/columns 均为内部常量，不含用户输入）。"""
        cursor = await conn.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in await cursor.fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
                logger.info("迁移：%s 表新增 %s 列", table, name)

    @staticmethod
    async def _backfill_members(conn) -> None:
        """历史数据回填（幂等）：账号补主成员，空归属的会话归到该账号的主成员。"""
        await conn.execute(
            """
            INSERT INTO members (member_id, username, display_name)
            SELECT username, username, '本人' FROM users
            WHERE NOT EXISTS (
                SELECT 1 FROM members WHERE members.member_id = users.username
            )
            """
        )
        await conn.execute(
            "UPDATE threads SET member_id = username "
            "WHERE member_id = '' OR member_id IS NULL"
        )

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

    # ==================== 咨询人管理（BaseMemberStore）====================

    async def list_members(self, username: str) -> list[Member]:
        """列出账号下所有咨询人（主成员在前，其余按创建时间升序）。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    """
                    SELECT member_id, username, display_name, created_at FROM members
                    WHERE username = ?
                    ORDER BY CASE WHEN member_id = username THEN 0 ELSE 1 END, created_at ASC
                    """,
                    (username,),
                )
                rows = await cursor.fetchall()
                return [
                    Member(
                        member_id=r["member_id"],
                        username=r["username"],
                        display_name=r["display_name"],
                        created_at=r["created_at"] or "",
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.warning("获取咨询人列表失败: %s", e)
            return []

    async def get_member(self, member_id: str) -> Member | None:
        """按 ID 获取咨询人；不存在返回 None。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT member_id, username, display_name, created_at "
                    "FROM members WHERE member_id = ?",
                    (member_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return Member(
                        member_id=row["member_id"],
                        username=row["username"],
                        display_name=row["display_name"],
                        created_at=row["created_at"] or "",
                    )
        except Exception as e:
            logger.warning("读取咨询人失败: %s", e)
        return None

    async def create_member(
        self, username: str, display_name: str, member_id: str | None = None
    ) -> Member:
        """创建咨询人（member_id 为空时生成 uuid4）。"""
        import uuid

        new_id = member_id or str(uuid.uuid4())
        name = (display_name or "").strip() or "家人"
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT INTO members (member_id, username, display_name) VALUES (?, ?, ?)",
                    (new_id, username, name),
                )
            logger.info("咨询人已创建: user=%s, member=%s, name=%s", username, new_id, name)
            return Member(member_id=new_id, username=username, display_name=name)
        except Exception as e:
            raise StorageError(f"创建咨询人失败: {e}") from e

    async def rename_member(
        self, member_id: str, display_name: str, username: str
    ) -> bool:
        """重命名咨询人（仅限归属账号）；返回是否命中。"""
        name = (display_name or "").strip()
        if not name:
            return False
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "UPDATE members SET display_name = ? WHERE member_id = ? AND username = ?",
                    (name, member_id, username),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.warning("重命名咨询人失败: %s", e)
            return False

    async def delete_member(self, member_id: str, username: str) -> bool:
        """
        删除咨询人及其画像、会话（仅限归属账号）。

        拒绝删除主成员（member_id == username）与账号下最后一个成员：
        主成员是账号本身的画像槽位，删掉会导致后续对话无画像可写。
        """
        if member_id == username:
            logger.info("拒绝删除主成员: %s", member_id)
            return False
        try:
            members = await self.list_members(username)
            if len(members) <= 1:
                logger.info("拒绝删除最后一个咨询人: %s", member_id)
                return False
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "DELETE FROM members WHERE member_id = ? AND username = ?",
                    (member_id, username),
                )
                if cursor.rowcount <= 0:
                    return False
                await conn.execute("DELETE FROM profiles WHERE patient_id = ?", (member_id,))
                await conn.execute("DELETE FROM threads WHERE member_id = ?", (member_id,))
            logger.info("咨询人已删除: user=%s, member=%s", username, member_id)
            return True
        except Exception as e:
            logger.warning("删除咨询人失败: %s", e)
            return False

    async def ensure_primary_member(self, username: str) -> Member:
        """确保账号存在主成员（member_id == username），返回该成员。

        用 INSERT OR IGNORE + 回读，避免并发首次访问时的 UNIQUE 冲突。
        """
        existing = await self.get_member(username)
        if existing is not None:
            return existing
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT OR IGNORE INTO members (member_id, username, display_name) "
                    "VALUES (?, ?, '本人')",
                    (username, username),
                )
        except Exception as e:
            logger.warning("补建主成员失败: %s", e)
        member = await self.get_member(username)
        if member is not None:
            return member
        raise StorageError(f"无法初始化主成员: {username}")

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
                    # 新列可能在旧库迁移前不存在，统一安全访问
                    keys = set(row.keys())

                    def col(name: str, default=None):
                        return row[name] if name in keys else default

                    return UserProfile(
                        patient_id=patient_id,
                        constitution=row["constitution"] or "未知",
                        allergies=row["allergies"] or "无",
                        past_history=json.loads(row["past_history"]) if row["past_history"] else [],
                        constitution_history=json.loads(col("constitution_history") or "[]"),
                        birth_year=col("birth_year"),
                        gender=col("gender") or "",
                        medical_history=json.loads(col("medical_history") or "[]"),
                    )
        except Exception as e:
            logger.warning("读取画像失败: %s", e)

        return UserProfile(patient_id=patient_id)

    async def update_profile(self, patient_id: str, data: dict[str, Any]) -> None:
        """
        更新患者画像（合并语义）。

        - allergies: 提取值非"无"/空时与现有取并集去重；为"无"/空时保留现有（永不覆盖）。
          过敏原为医学安全数据，只增不减。
        - constitution: 提取值非"未知"/空且与现值不同时更新，旧值追加到 constitution_history；
          为"未知"/空时保留现有。
        - new_record: 追加到 past_history（最多 10 条）。
        """
        try:
            current = await self.get_profile(patient_id)

            # --- 过敏原：合并去重，永不回退为"无" ---
            merged_allergies = self._merge_allergies(
                current.allergies, (data.get("allergies") or "").strip()
            )

            # --- 体质：新值有效且不同才更新，旧值入历史 ---
            raw_constitution = (data.get("constitution") or "").strip()
            new_constitution = current.constitution
            new_constitution_history = list(current.constitution_history)
            if (
                raw_constitution
                and raw_constitution != "未知"
                and raw_constitution != current.constitution
            ):
                if current.constitution and current.constitution != "未知":
                    new_constitution_history.append(current.constitution)
                new_constitution = raw_constitution

            # --- 诊疗记录：追加 ---
            past_history = list(current.past_history)
            if data.get("new_record"):
                past_history.append(data["new_record"])
                past_history = past_history[-10:]

            # --- 出生年份/性别：新值有效才覆盖（空值永不覆盖） ---
            new_birth_year = current.birth_year
            raw_birth_year = data.get("birth_year")
            if isinstance(raw_birth_year, int) and 1900 <= raw_birth_year <= 2100:
                new_birth_year = raw_birth_year

            new_gender = current.gender
            raw_gender = str(data.get("gender") or "").strip().lower()
            if raw_gender in ("male", "female") and raw_gender != current.gender:
                new_gender = raw_gender

            # --- 既往病史：按名称并集去重 ---
            new_medical_history = self._merge_medical_history(
                current.medical_history, data.get("medical_history") or []
            )

            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO profiles
                        (patient_id, constitution, allergies, past_history, constitution_history,
                         birth_year, gender, medical_history, last_update)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(patient_id) DO UPDATE SET
                        constitution = excluded.constitution,
                        allergies = excluded.allergies,
                        past_history = excluded.past_history,
                        constitution_history = excluded.constitution_history,
                        birth_year = excluded.birth_year,
                        gender = excluded.gender,
                        medical_history = excluded.medical_history,
                        last_update = CURRENT_TIMESTAMP
                    """,
                    (
                        patient_id,
                        new_constitution,
                        merged_allergies,
                        json.dumps(past_history, ensure_ascii=False),
                        json.dumps(new_constitution_history, ensure_ascii=False),
                        new_birth_year,
                        new_gender,
                        json.dumps(new_medical_history, ensure_ascii=False),
                    ),
                )
            logger.info(
                "画像已更新: %s (体质=%s, 过敏=%s)", patient_id, new_constitution, merged_allergies
            )
        except Exception as e:
            raise StorageError(f"更新画像失败: {e}") from e

    @staticmethod
    def _merge_allergies(existing: str, new: str) -> str:
        """合并过敏原：现有与新增取并集去重（规范化名称）；空/无 不覆盖现有。"""
        import re

        def normalize(s: str) -> str:
            """去除 LLM 常附加的冗余后缀（过敏/及相关制品/类药物），便于去重。"""
            t = (s or "").strip()
            prev = None
            while prev != t:
                prev = t
                t = re.sub(r"(及相关制品|及制品|相关制品|类药物|过敏)+$", "", t).strip()
            return t or (s or "").strip()

        def parse(s: str) -> list[str]:
            if not s or s.strip() in ("", "无", "未知"):
                return []
            parts = re.split(r"[、，,；;]\s*", s.strip())
            return [
                normalize(p)
                for p in parts
                if p.strip() and p.strip() not in ("无", "未知")
            ]

        items: list[str] = []
        seen: set[str] = set()
        for item in parse(existing) + parse(new):
            if item and item not in seen:
                seen.add(item)
                items.append(item)
        return "、".join(items) if items else "无"

    @staticmethod
    def _merge_medical_history(existing: list, new: list) -> list[dict]:
        """
        合并既往病史：按名称去重，新条目覆盖同名的 status/since_year/note。

        条目形状: {"name": "高血压", "status": "active"|"history",
                  "since_year": 2018|null, "note": ""}
        兼容纯字符串条目（按现患处理）。
        """
        merged: dict[str, dict] = {}
        for item in list(existing or []) + list(new or []):
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            cur = merged.get(
                name, {"name": name, "status": "active", "since_year": None, "note": ""}
            )
            status = str(item.get("status") or "").strip()
            if status in ("active", "history"):
                cur["status"] = status
            since = item.get("since_year")
            if isinstance(since, int) and 1900 <= since <= 2100:
                cur["since_year"] = since
            note = str(item.get("note") or "").strip()
            if note:
                cur["note"] = note
            merged[name] = cur
        return list(merged.values())

    async def set_profile_fields(self, patient_id: str, fields: dict[str, Any]) -> None:
        """
        手动编辑画像：只覆盖传入的字段（覆盖语义，与 update_profile 的合并语义不同）。

        支持的字段: birth_year / gender / medical_history。
        """
        try:
            current = await self.get_profile(patient_id)
            birth_year = current.birth_year
            if "birth_year" in fields:
                raw = fields.get("birth_year")
                birth_year = raw if isinstance(raw, int) and 1900 <= raw <= 2100 else None

            gender = current.gender
            if "gender" in fields:
                raw = str(fields.get("gender") or "").strip().lower()
                gender = raw if raw in ("male", "female") else ""

            medical_history = current.medical_history
            if "medical_history" in fields:
                medical_history = self._merge_medical_history([], fields.get("medical_history"))

            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO profiles
                        (patient_id, constitution, allergies, past_history, constitution_history,
                         birth_year, gender, medical_history, last_update)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(patient_id) DO UPDATE SET
                        birth_year = excluded.birth_year,
                        gender = excluded.gender,
                        medical_history = excluded.medical_history,
                        last_update = CURRENT_TIMESTAMP
                    """,
                    (
                        patient_id,
                        current.constitution,
                        current.allergies,
                        json.dumps(current.past_history, ensure_ascii=False),
                        json.dumps(current.constitution_history, ensure_ascii=False),
                        birth_year,
                        gender,
                        json.dumps(medical_history, ensure_ascii=False),
                    ),
                )
            logger.info("画像字段已手动更新: %s (%s)", patient_id, sorted(fields))
        except Exception as e:
            raise StorageError(f"更新画像字段失败: {e}") from e

    async def set_allergies(self, patient_id: str, allergies: str) -> None:
        """
        直接设置过敏史（覆盖语义，不走合并）。

        用于手动编辑和移除过敏原。与 update_profile 的合并语义不同，
        此方法直接覆盖整个 allergies 字段。
        """
        try:
            current = await self.get_profile(patient_id)
            allergies = (allergies or "").strip() or "无"
            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO profiles
                        (patient_id, constitution, allergies, past_history, constitution_history, last_update)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(patient_id) DO UPDATE SET
                        allergies = excluded.allergies,
                        last_update = CURRENT_TIMESTAMP
                    """,
                    (
                        patient_id,
                        current.constitution,
                        allergies,
                        json.dumps(current.past_history, ensure_ascii=False),
                        json.dumps(current.constitution_history, ensure_ascii=False),
                    ),
                )
            logger.info("过敏史已直接设置: %s (过敏=%s)", patient_id, allergies)
        except Exception as e:
            raise StorageError(f"设置过敏史失败: {e}") from e

    async def list_profiles(self, username: str | None = None) -> list[dict[str, str]]:
        """列出患者画像（按最后更新时间降序）；指定 username 时仅限该账号的咨询人。"""
        try:
            async with self._transaction() as conn:
                if username is None:
                    cursor = await conn.execute(
                        "SELECT patient_id, last_update FROM profiles ORDER BY last_update DESC"
                    )
                else:
                    cursor = await conn.execute(
                        """
                        SELECT patient_id, last_update FROM profiles
                        WHERE patient_id IN (
                            SELECT member_id FROM members WHERE username = ?
                        )
                        ORDER BY last_update DESC
                        """,
                        (username,),
                    )
                rows = await cursor.fetchall()
                return [{"patient_id": r["patient_id"], "last_update": r["last_update"]} for r in rows]
        except Exception as e:
            logger.warning("获取画像列表失败: %s", e)
            return []

    # ==================== 线程管理（BaseThreadStore）====================

    async def add_thread(
        self, username: str, thread_id: str, member_id: str = "", title: str = "新对话"
    ) -> None:
        """创建会话线程；已存在时只更新咨询人归属（不覆盖用户已改的标题）。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO threads (thread_id, username, member_id, title)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(thread_id) DO UPDATE SET member_id = excluded.member_id
                    """,
                    (thread_id, username, member_id, title or "新对话"),
                )
        except Exception as e:
            logger.warning("创建线程失败: %s", e)

    async def get_threads(
        self, username: str, member_id: str | None = None
    ) -> list[ThreadInfo]:
        """获取用户的会话线程（按创建时间降序）；member_id 非 None 时按咨询人筛选。"""
        try:
            async with self._transaction() as conn:
                if member_id is None:
                    cursor = await conn.execute(
                        "SELECT thread_id, title, created_at, member_id FROM threads "
                        "WHERE username = ? ORDER BY created_at DESC",
                        (username,),
                    )
                else:
                    cursor = await conn.execute(
                        "SELECT thread_id, title, created_at, member_id FROM threads "
                        "WHERE username = ? AND member_id = ? ORDER BY created_at DESC",
                        (username, member_id),
                    )
                rows = await cursor.fetchall()
                return [
                    ThreadInfo(
                        thread_id=r["thread_id"],
                        username=username,
                        title=r["title"] or "新对话",
                        created_at=r["created_at"] or "",
                        member_id=r["member_id"] or "",
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.warning("获取线程列表失败: %s", e)
            return []

    async def get_thread(self, thread_id: str) -> ThreadInfo | None:
        """按 ID 获取会话线程；不存在返回 None（供画像写入守卫校验成员一致性）。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT thread_id, username, title, created_at, member_id "
                    "FROM threads WHERE thread_id = ?",
                    (thread_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return ThreadInfo(
                        thread_id=row["thread_id"],
                        username=row["username"],
                        title=row["title"] or "新对话",
                        created_at=row["created_at"] or "",
                        member_id=row["member_id"] or "",
                    )
        except Exception as e:
            logger.warning("读取线程失败: %s", e)
        return None

    async def rename_thread(
        self, thread_id: str, new_title: str, username: str
    ) -> bool:
        """重命名会话线程（仅限归属用户）。返回是否命中。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "UPDATE threads SET title = ? WHERE thread_id = ? AND username = ?",
                    (new_title, thread_id, username),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.warning("重命名线程失败: %s", e)
            return False

    async def delete_thread(self, thread_id: str, username: str) -> bool:
        """删除会话线程（仅限归属用户）。返回是否命中。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "DELETE FROM threads WHERE thread_id = ? AND username = ?",
                    (thread_id, username),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.warning("删除线程失败: %s", e)
            return False

    # ==================== 本草知识库（BaseHerbStore）====================

    async def upsert_herb(self, herb: Herb) -> None:
        """插入或更新本草记录（upsert 语义，供 seed 脚本调用）。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO herbs
                        (name, aliases, nature_flavor, meridians, efficacy,
                         indications, dosage, processing, contraindications)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        aliases = excluded.aliases,
                        nature_flavor = excluded.nature_flavor,
                        meridians = excluded.meridians,
                        efficacy = excluded.efficacy,
                        indications = excluded.indications,
                        dosage = excluded.dosage,
                        processing = excluded.processing,
                        contraindications = excluded.contraindications
                    """,
                    (
                        herb.name,
                        json.dumps(herb.aliases, ensure_ascii=False),
                        herb.nature_flavor,
                        json.dumps(herb.meridians, ensure_ascii=False),
                        herb.efficacy,
                        json.dumps(herb.indications, ensure_ascii=False),
                        herb.dosage,
                        herb.processing,
                        herb.contraindications,
                    ),
                )
        except Exception as e:
            logger.warning("写入本草失败: %s", e)

    async def get_herb(self, name: str) -> Herb | None:
        """按正名精确获取本草信息。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM herbs WHERE name = ?", (name,)
                )
                row = await cursor.fetchone()
                if row:
                    return self._row_to_herb(row)
        except Exception as e:
            logger.warning("读取本草失败: %s", e)
        return None

    async def search_herbs(self, query: str) -> list[Herb]:
        """按关键词模糊搜索本草（匹配正名、别名、功效、主治）。"""
        try:
            pattern = f"%{query}%"
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    """
                    SELECT * FROM herbs
                    WHERE name LIKE ? OR aliases LIKE ?
                       OR efficacy LIKE ? OR indications LIKE ?
                    """,
                    (pattern, pattern, pattern, pattern),
                )
                rows = await cursor.fetchall()
                return [self._row_to_herb(r) for r in rows]
        except Exception as e:
            logger.warning("搜索本草失败: %s", e)
            return []

    @staticmethod
    def _row_to_herb(row) -> Herb:
        """将数据库行转换为 Herb 实例。"""
        return Herb(
            name=row["name"],
            aliases=json.loads(row["aliases"]) if row["aliases"] else [],
            nature_flavor=row["nature_flavor"] or "",
            meridians=json.loads(row["meridians"]) if row["meridians"] else [],
            efficacy=row["efficacy"] or "",
            indications=json.loads(row["indications"]) if row["indications"] else [],
            dosage=row["dosage"] or "",
            processing=row["processing"] or "",
            contraindications=row["contraindications"] or "",
        )

    # ==================== 方剂知识库（BaseFormulaStore）====================

    async def upsert_formula(self, formula: Formula) -> None:
        """插入或更新方剂记录（upsert 语义，供 seed 脚本调用）。"""
        try:
            async with self._transaction() as conn:
                composition_data = [
                    {"herb": c.herb, "dosage": c.dosage} for c in formula.composition
                ]
                await conn.execute(
                    """
                    INSERT INTO formulas
                        (name, source, composition, indication,
                         modifications, contraindications, category)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        source = excluded.source,
                        composition = excluded.composition,
                        indication = excluded.indication,
                        modifications = excluded.modifications,
                        contraindications = excluded.contraindications,
                        category = excluded.category
                    """,
                    (
                        formula.name,
                        formula.source,
                        json.dumps(composition_data, ensure_ascii=False),
                        formula.indication,
                        formula.modifications,
                        formula.contraindications,
                        formula.category,
                    ),
                )
        except Exception as e:
            logger.warning("写入方剂失败: %s", e)

    async def get_formula(self, name: str) -> Formula | None:
        """按名称精确获取方剂信息。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM formulas WHERE name = ?", (name,)
                )
                row = await cursor.fetchone()
                if row:
                    return self._row_to_formula(row)
        except Exception as e:
            logger.warning("读取方剂失败: %s", e)
        return None

    async def search_formulas(self, syndrome_or_keyword: str) -> list[Formula]:
        """按证候或关键词模糊搜索方剂（匹配名称、主治、组成）。"""
        try:
            pattern = f"%{syndrome_or_keyword}%"
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    """
                    SELECT * FROM formulas
                    WHERE name LIKE ? OR indication LIKE ? OR composition LIKE ?
                    """,
                    (pattern, pattern, pattern),
                )
                rows = await cursor.fetchall()
                return [self._row_to_formula(r) for r in rows]
        except Exception as e:
            logger.warning("搜索方剂失败: %s", e)
            return []

    @staticmethod
    def _row_to_formula(row) -> Formula:
        """将数据库行转换为 Formula 实例。"""
        composition_raw = json.loads(row["composition"]) if row["composition"] else []
        composition = [
            FormulaComponent(herb=c.get("herb", ""), dosage=c.get("dosage", ""))
            for c in composition_raw
        ]
        return Formula(
            name=row["name"],
            source=row["source"] or "",
            composition=composition,
            indication=row["indication"] or "",
            modifications=row["modifications"] or "",
            contraindications=row["contraindications"] or "",
            category=row["category"] or "",
        )

    # ==================== 禁忌知识库（BaseContraindicationStore）====================

    async def add_contraindication(self, ci: Contraindication) -> None:
        """添加禁忌条目（幂等：同 herb+type+detail+severity 不重复插入，供 seed 脚本调用）。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO contraindications (herb, type, detail, severity)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ci.herb, ci.type, ci.detail, ci.severity),
                )
        except Exception as e:
            logger.warning("写入禁忌失败: %s", e)

    async def get_contraindications(self, herb: str) -> list[Contraindication]:
        """查询某味药的所有禁忌条目。"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT * FROM contraindications WHERE herb = ?", (herb,)
                )
                rows = await cursor.fetchall()
                return [
                    Contraindication(
                        herb=r["herb"],
                        type=r["type"] or "",
                        detail=r["detail"] or "",
                        severity=r["severity"] or "",
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.warning("读取禁忌失败: %s", e)
            return []
