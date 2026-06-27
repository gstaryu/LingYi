"""
FastAPI 应用工厂 — 创建和配置 FastAPI 应用实例。

使用 lifespan 管理应用启动和关闭时的资源初始化/清理。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lingyi.api.deps import get_storage
from lingyi.config import get_settings
from lingyi.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("灵医 API 启动中... 环境: %s", settings.environment)

    # 初始化数据库
    storage = get_storage(settings)
    await storage.init_db()

    yield

    logger.info("灵医 API 关闭")


def create_app() -> FastAPI:
    """
    创建 FastAPI 应用实例。

    Returns:
        配置好的 FastAPI 实例
    """
    settings = get_settings()

    app = FastAPI(
        title="灵医 API",
        description="基于 LangGraph 的中医诊疗多智能体系统",
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    from lingyi.api.routes import auth, chat, health, profiles, threads
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(threads.router, prefix="/api", tags=["threads"])
    app.include_router(profiles.router, prefix="/api", tags=["profiles"])

    return app


# 应用实例（uvicorn 直接引用）
app = create_app()
