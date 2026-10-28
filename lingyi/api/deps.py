"""
FastAPI 依赖注入 - 基于 app.state 的实例共享 + JWT 认证。

设计原则:
- 不使用模块级全局单例（原 _agent_instance 等导致测试必须 reset_instances、无法多实例并行）
- 重型实例在 lifespan 中创建并存入 app.state，请求级通过 Depends 读取
- get_current_user 解码 Bearer JWT，返回用户名，保护需认证的路由
- 测试通过 app.dependency_overrides 注入桩实例，无需真实 API
"""

import logging
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from lingyi.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Bearer Token 提取器（auto_error=False 以便自定义 401 响应）
_bearer = HTTPBearer(auto_error=False)


def get_settings_dep() -> Settings:
    """FastAPI 依赖入口：获取全局配置。"""
    return get_settings()


def get_storage(request: Request) -> Any:
    """从 app.state 获取存储实例（lifespan 中创建）。"""
    return request.app.state.storage


def get_safety_engine(request: Request) -> Any:
    """从 app.state 获取安全引擎实例。"""
    return request.app.state.safety_engine


def get_rag_client(request: Request) -> Any:
    """从 app.state 获取 RAG 客户端实例。"""
    return request.app.state.rag_client


def get_agent(request: Request) -> Any:
    """从 app.state 获取已编译的 Agent 图。"""
    agent = request.app.state.agent
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent 未初始化（未配置 API Key 或正在测试中）",
        )
    return agent


def decode_access_token(token: str | None) -> str:
    """
    解码 JWT token，返回用户名。无效或缺失则抛 HTTPException 401。

    供 HTTP Bearer 依赖与 WebSocket query-param 鉴权共用，避免逻辑重复。

    Raises:
        HTTPException 401 - 未提供凭据或 Token 无效
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 验证失败",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少用户信息",
        )
    return username


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """
    解码 Bearer JWT，返回用户名（FastAPI 依赖入口）。

    Returns:
        认证用户的用户名

    Raises:
        HTTPException 401 - 未提供凭据或 Token 无效
    """
    return decode_access_token(credentials.credentials if credentials else None)


async def resolve_member_id(
    storage: Any, username: str, member_id: str | None
) -> str:
    """
    把请求中的 member_id 解析为可信的咨询人 ID。

    - None：未指定，回退到主成员（member_id == username）
    - ""：显式"不结合咨询人"，原样返回空串（不加载、不写入画像）
    - 其他值：必须是当前账号下的咨询人，否则 404（不区分"不存在"与"不归属"，
      避免暴露他人咨询人是否存在）

    Raises:
        HTTPException 404 - 咨询人不存在或不归属当前账号
    """
    if member_id == "":
        return ""
    if member_id is None:
        primary = await storage.ensure_primary_member(username)
        return primary.member_id

    member = await storage.get_member(member_id)
    if member is None or member.username != username:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="咨询人不存在或不归属当前账号",
        )
    return member.member_id
