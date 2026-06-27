"""
存储抽象层 — 用户、画像、线程管理的抽象基类。

设计原则:
- 所有存储操作均为异步（aiosqlite）
- 接口与实现分离，便于切换存储后端（SQLite / PostgreSQL / etc.）
- 密码哈希使用 bcrypt（比 SHA-256 更安全）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserProfile:
    """患者画像数据。"""

    patient_id: str
    """患者 ID（通常等于 username）。"""

    constitution: str = "未知"
    """体质类型（如阳虚、阴虚、痰湿等）。"""

    allergies: str = "无"
    """过敏史。"""

    past_history: list[str] = field(default_factory=list)
    """既往有效处方记录（最多保留 10 条）。"""


@dataclass
class ThreadInfo:
    """会话线程信息。"""

    thread_id: str
    """线程唯一标识。"""

    username: str
    """所属用户名。"""

    title: str = "新对话"
    """线程标题。"""

    created_at: str = ""
    """创建时间。"""


class BaseUserStore(ABC):
    """用户管理抽象基类。"""

    @abstractmethod
    async def create_user(self, username: str, password: str) -> bool:
        """
        创建新用户。

        Args:
            username: 用户名
            password: 明文密码（实现层负责哈希）

        Returns:
            True 创建成功，False 用户已存在
        """

    @abstractmethod
    async def verify_user(self, username: str, password: str) -> bool:
        """
        验证用户密码。

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            True 验证通过
        """


class BaseProfileStore(ABC):
    """患者画像管理抽象基类。"""

    @abstractmethod
    async def get_profile(self, patient_id: str) -> UserProfile:
        """
        获取患者画像。

        Args:
            patient_id: 患者 ID

        Returns:
            UserProfile 实例
        """

    @abstractmethod
    async def update_profile(self, patient_id: str, data: dict[str, Any]) -> None:
        """
        更新患者画像（upsert 语义）。

        Args:
            patient_id: 患者 ID
            data: 待更新的字段（constitution, allergies, new_record）
        """

    @abstractmethod
    async def list_profiles(self) -> list[dict[str, str]]:
        """
        列出所有患者画像（按最后更新时间降序）。

        Returns:
            [{"patient_id": "...", "last_update": "..."}]
        """


class BaseThreadStore(ABC):
    """会话线程管理抽象基类。"""

    @abstractmethod
    async def add_thread(self, username: str, thread_id: str) -> None:
        """
        创建新会话线程。

        Args:
            username: 用户名
            thread_id: 线程 ID
        """

    @abstractmethod
    async def get_threads(self, username: str) -> list[ThreadInfo]:
        """
        获取用户的所有会话线程。

        Args:
            username: 用户名

        Returns:
            ThreadInfo 列表（按创建时间降序）
        """

    @abstractmethod
    async def rename_thread(self, thread_id: str, new_title: str) -> None:
        """
        重命名会话线程。

        Args:
            thread_id: 线程 ID
            new_title: 新标题
        """

    @abstractmethod
    async def delete_thread(self, thread_id: str) -> None:
        """
        删除会话线程。

        Args:
            thread_id: 线程 ID
        """
