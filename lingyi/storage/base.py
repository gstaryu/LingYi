"""
存储抽象层 — 用户、画像、线程管理的抽象基类。

设计原则:
- 所有存储操作均为异步（aiosqlite）
- 接口与实现分离，便于切换存储后端（SQLite / PostgreSQL / etc.）
- 密码哈希使用 bcrypt（比 SHA-256 更安全）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from lingyi.knowledge.models import Contraindication, Formula, Herb


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

    constitution_history: list[str] = field(default_factory=list)
    """体质变更历史（旧体质值按时间追加，便于追溯；空表示从未变更）。"""

    birth_year: int | None = None
    """出生年份。存年份而非年龄，避免随时间过期；年龄由 `age` 属性按当前年份换算。"""

    gender: str = ""
    """性别："" | "male" | "female"。空表示未采集，禁止推断。"""

    medical_history: list[dict[str, Any]] = field(default_factory=list)
    """既往病史：[{"name": "高血压", "status": "active|history", "since_year": 2018, "note": ""}]。"""

    @property
    def age(self) -> int | None:
        """按当前年份换算年龄；未采集出生年份时返回 None。"""
        if not self.birth_year:
            return None
        return date.today().year - self.birth_year


@dataclass
class Member:
    """咨询人（账号下的家庭成员）。"""

    member_id: str
    """成员唯一标识（主成员等于 username，兼容多成员上线前的历史数据）。"""

    username: str
    """归属账号。"""

    display_name: str
    """显示名（如"本人"、"母亲"）。"""

    created_at: str = ""
    """创建时间。"""


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

    member_id: str = ""
    """该会话使用的咨询人（空表示不结合咨询人的通用问答）。"""


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


class BaseMemberStore(ABC):
    """咨询人（家庭成员）管理抽象基类。"""

    @abstractmethod
    async def list_members(self, username: str) -> list[Member]:
        """列出账号下所有咨询人（主成员在前，其余按创建时间升序）。"""

    @abstractmethod
    async def get_member(self, member_id: str) -> Member | None:
        """按 ID 获取咨询人；不存在返回 None。"""

    @abstractmethod
    async def create_member(
        self, username: str, display_name: str, member_id: str | None = None
    ) -> Member:
        """创建咨询人（member_id 为空时生成 uuid4）。"""

    @abstractmethod
    async def rename_member(
        self, member_id: str, display_name: str, username: str
    ) -> bool:
        """重命名咨询人（仅限归属账号）；返回是否命中。"""

    @abstractmethod
    async def delete_member(self, member_id: str, username: str) -> bool:
        """删除咨询人及其画像与会话（仅限归属账号）；返回是否命中。"""

    @abstractmethod
    async def ensure_primary_member(self, username: str) -> Member:
        """确保账号存在主成员（member_id == username），返回该成员。"""


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
    async def set_allergies(self, patient_id: str, allergies: str) -> None:
        """
        直接设置过敏史（覆盖语义，不走合并）。

        用于手动编辑过敏史和移除过敏原（"我对X不过敏了"）。
        与 update_profile 的合并语义不同，此方法直接覆盖整个 allergies 字段。

        Args:
            patient_id: 患者 ID
            allergies: 完整的过敏史字符串（如"青霉素、海鲜"或"无"）
        """

    @abstractmethod
    async def list_profiles(self, username: str | None = None) -> list[dict[str, str]]:
        """
        列出患者画像（按最后更新时间降序）。

        Args:
            username: 限定为该账号下咨询人的画像；None 表示不限（仅供运维脚本使用）

        Returns:
            [{"patient_id": "...", "last_update": "..."}]
        """


class BaseThreadStore(ABC):
    """会话线程管理抽象基类。"""

    @abstractmethod
    async def add_thread(
        self, username: str, thread_id: str, member_id: str = "", title: str = "新对话"
    ) -> None:
        """
        创建新会话线程（已存在时只更新咨询人归属，不改标题）。

        Args:
            username: 用户名
            thread_id: 线程 ID
            member_id: 该会话使用的咨询人；空表示不结合咨询人
            title: 初始标题（仅在新建时生效）
        """

    @abstractmethod
    async def get_threads(
        self, username: str, member_id: str | None = None
    ) -> list[ThreadInfo]:
        """
        获取用户的会话线程。

        Args:
            username: 用户名
            member_id: 仅返回该咨询人的会话；None 表示不筛选

        Returns:
            ThreadInfo 列表（按创建时间降序）
        """

    @abstractmethod
    async def rename_thread(
        self, thread_id: str, new_title: str, username: str
    ) -> bool:
        """
        重命名会话线程（仅限归属用户）。

        Args:
            thread_id: 线程 ID
            new_title: 新标题
            username: 当前认证用户（用于归属校验）

        Returns:
            True 命中并重命名；False 表示线程不存在或不归属该用户
        """

    @abstractmethod
    async def delete_thread(self, thread_id: str, username: str) -> bool:
        """
        删除会话线程（仅限归属用户）。

        Args:
            thread_id: 线程 ID
            username: 当前认证用户（用于归属校验）

        Returns:
            True 命中并删除；False 表示线程不存在或不归属该用户
        """


class BaseHerbStore(ABC):
    """本草（中药）知识库抽象基类。"""

    @abstractmethod
    async def get_herb(self, name: str) -> Herb | None:
        """
        按正名精确获取本草信息。

        Args:
            name: 药材正名

        Returns:
            Herb 实例，不存在时返回 None
        """

    @abstractmethod
    async def search_herbs(self, query: str) -> list[Herb]:
        """
        按关键词模糊搜索本草（匹配正名、别名、功效、主治）。

        Args:
            query: 搜索关键词

        Returns:
            匹配的 Herb 列表（空列表表示无结果）
        """


class BaseFormulaStore(ABC):
    """方剂知识库抽象基类。"""

    @abstractmethod
    async def get_formula(self, name: str) -> Formula | None:
        """
        按名称精确获取方剂信息。

        Args:
            name: 方剂名称

        Returns:
            Formula 实例，不存在时返回 None
        """

    @abstractmethod
    async def search_formulas(self, syndrome_or_keyword: str) -> list[Formula]:
        """
        按证候或关键词模糊搜索方剂（匹配名称、主治、组成）。

        Args:
            syndrome_or_keyword: 证候或关键词

        Returns:
            匹配的 Formula 列表（空列表表示无结果）
        """


class BaseContraindicationStore(ABC):
    """中药禁忌知识库抽象基类。"""

    @abstractmethod
    async def get_contraindications(self, herb: str) -> list[Contraindication]:
        """
        查询某味药的所有禁忌条目。

        Args:
            herb: 药材名称

        Returns:
            Contraindication 列表（空列表表示无禁忌记录）
        """
