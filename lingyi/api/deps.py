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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """
    解码 Bearer JWT，返回用户名。

    Returns:
        认证用户的用户名

    Raises:
        HTTPException 401 - 未提供凭据或 Token 无效
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
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
