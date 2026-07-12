"""认证路由 — 登录/注册/JWT Token。"""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException

from lingyi.api.deps import get_storage, get_settings
from lingyi.api.schemas import TokenResponse, UserLogin, UserRegister

logger = logging.getLogger(__name__)
router = APIRouter()


def _create_token(username: str) -> str:
    """创建 JWT Token。"""
    settings = get_settings()
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLogin):
    """用户登录，返回 JWT Token。"""
    storage = get_storage()
    verified = await storage.verify_user(request.username, request.password)
    if not verified:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = _create_token(request.username)
    logger.info("用户登录成功: %s", request.username)
    return TokenResponse(access_token=token)


@router.post("/register")
async def register(request: UserRegister):
    """用户注册。"""
    storage = get_storage()
    created = await storage.create_user(request.username, request.password)
    if not created:
        raise HTTPException(status_code=400, detail="用户名已存在")

    logger.info("用户注册成功: %s", request.username)
    return {"status": "ok", "message": "注册成功"}
