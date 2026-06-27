"""
Pydantic 模型 — API 请求/响应的数据结构定义。
"""

from pydantic import BaseModel, Field


# ==================== 聊天 ====================

class ChatRequest(BaseModel):
    """聊天请求。"""

    message: str = Field(..., description="用户消息内容")
    thread_id: str = Field(default="", description="会话线程 ID（为空时自动创建）")
    files: list[str] = Field(default_factory=list, description="上传的文件路径列表")


class ChatResponse(BaseModel):
    """聊天响应。"""

    response: str = Field(..., description="AI 回复内容")
    thread_id: str = Field(..., description="会话线程 ID")
    intent_type: str = Field(default="chat", description="识别到的意图类型")
    symptoms: list[str] = Field(default_factory=list, description="提取的症状列表")


# ==================== 线程 ====================

class ThreadCreate(BaseModel):
    """创建线程请求。"""

    title: str = Field(default="新对话", description="线程标题")


class ThreadResponse(BaseModel):
    """线程信息。"""

    thread_id: str
    title: str
    created_at: str


class ThreadRename(BaseModel):
    """重命名线程请求。"""

    new_title: str = Field(..., description="新标题")


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

class ProfileResponse(BaseModel):
    """患者画像。"""

    patient_id: str
    constitution: str = "未知"
    allergies: str = "无"
    past_history: list[str] = Field(default_factory=list)


# ==================== 健康检查 ====================

class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "ok"
    version: str = "2.0.0"
    rag_mode: str = "mock"
