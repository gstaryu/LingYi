"""
Pydantic 模型 — API 请求/响应的数据结构定义。
"""

from pydantic import BaseModel, Field


# ==================== 聊天 ====================

class ChatRequest(BaseModel):
    """聊天请求。"""

    message: str = Field(..., max_length=10000, description="用户消息内容")
    thread_id: str = Field(default="", description="会话线程 ID（为空时自动创建）")
    files: list[str] = Field(default_factory=list, max_length=10, description="上传的文件路径列表")
    member_id: str | None = Field(
        default=None,
        description='咨询人 ID：None=默认主成员（本人）；""=不结合咨询人（不读写画像）；'
        "其他值须归属当前账号",
    )


class ChatResponse(BaseModel):
    """聊天响应。"""

    response: str = Field(..., description="AI 回复内容")
    thread_id: str = Field(..., description="会话线程 ID")
    intent_type: str = Field(default="chat", description="识别到的意图类型")
    symptoms: list[str] = Field(default_factory=list, description="提取的症状列表")


# ==================== 线程 ====================

class ThreadCreate(BaseModel):
    """创建线程请求。"""

    title: str = Field(default="新对话", max_length=100, description="线程标题")
    member_id: str | None = Field(default=None, description="咨询人 ID（None=主成员）")


class ThreadResponse(BaseModel):
    """线程信息。"""

    thread_id: str
    title: str
    created_at: str
    member_id: str = ""


# ==================== 咨询人 ====================

class MemberCreate(BaseModel):
    """新建咨询人请求。"""

    display_name: str = Field(..., max_length=30, description="显示名（如 母亲）")


class MemberRename(BaseModel):
    """重命名咨询人请求。"""

    display_name: str = Field(..., max_length=30, description="新显示名")


class MemberResponse(BaseModel):
    """咨询人信息。"""

    member_id: str
    display_name: str
    created_at: str = ""
    is_primary: bool = False


class ThreadRename(BaseModel):
    """重命名线程请求。"""

    new_title: str = Field(..., max_length=100, description="新标题")


# ==================== 用户 ====================

class UserLogin(BaseModel):
    """登录请求。"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserRegister(BaseModel):
    """注册请求。"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., min_length=6, description="密码（至少 6 位）")


class TokenResponse(BaseModel):
    """JWT Token 响应。"""

    access_token: str
    token_type: str = "bearer"


# ==================== 画像 ====================

class MedicalHistoryItem(BaseModel):
    """既往病史条目（AAFP 风格：名称 + 状态 + 起病年份）。"""

    name: str = Field(..., max_length=100, description="病名（如 高血压）")
    status: str = Field(default="active", description="active（现患）/ history（既往）")
    since_year: int | None = Field(default=None, description="起病年份（可空）")
    note: str = Field(default="", max_length=200, description="备注")


class ProfileResponse(BaseModel):
    """患者画像。"""

    patient_id: str
    constitution: str = "未知"
    allergies: str = "无"
    past_history: list[str] = Field(default_factory=list)
    birth_year: int | None = None
    age: int | None = Field(default=None, description="按当前年份换算的年龄")
    gender: str = ""
    medical_history: list[MedicalHistoryItem] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    """画像更新请求（手动编辑）。allergies 为完整覆盖，非合并。"""

    constitution: str | None = Field(default=None, description="体质类型（留空不修改）")
    allergies: str | None = Field(default=None, description="过敏史（完整覆盖，非合并）")
    birth_year: int | None = Field(default=None, description="出生年份（留空不修改）")
    age: int | None = Field(
        default=None, description="年龄（便捷字段，后端按当前年份换算为出生年份）"
    )
    gender: str | None = Field(default=None, description="性别：male / female / 空")
    medical_history: list[MedicalHistoryItem] | None = Field(
        default=None, description="既往病史（完整覆盖）"
    )


# ==================== 健康检查 ====================

class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "ok"
    version: str = "2.0.0"
    rag_mode: str = "mock"
