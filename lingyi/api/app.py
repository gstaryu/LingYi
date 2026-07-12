"""
FastAPI 应用工厂 - 创建和配置 FastAPI 应用实例。

使用 lifespan 管理应用启动/关闭：启动时创建所有重型实例（storage/safety/rag/agent）
并存入 app.state，请求级通过 Depends 读取；关闭时释放连接。
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lingyi.config import get_settings
from lingyi.logging import setup_logging

logger = logging.getLogger(__name__)


def _create_rag_client(settings):
    """根据配置创建 RAG 客户端（mock/chroma）。"""
    if settings.rag_mode == "chroma":
        from lingyi.models.factory import create_embeddings
        from lingyi.rag.chroma import ChromaRAGClient

        return ChromaRAGClient(
            chroma_db_dir=settings.chroma_db_dir,
            embedding_model=create_embeddings(settings),
        )
    from lingyi.rag.mock import MockRAGClient

    mock_data_path = os.path.join(settings.storage_dir, "mock_rag_data.json")
    return MockRAGClient(data_path=mock_data_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动创建实例并存入 app.state，关闭释放连接。"""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("灵医 API 启动中... 环境: %s, RAG 模式: %s", settings.environment, settings.rag_mode)

    # storage（始终创建，无 API 依赖）
    from lingyi.storage.sqlite import SQLiteStorage

    storage = SQLiteStorage(settings.db_path)
    await storage.init_db()
    app.state.storage = storage

    # safety engine（纯规则，无依赖）
    from lingyi.safety.rules import SafetyEngine

    app.state.safety_engine = SafetyEngine()

    # rag client（mock 模式无 API 依赖；chroma 模式需 embedding）
    app.state.rag_client = _create_rag_client(settings)

    # agent（需 LLM；未配置 API Key 时跳过，测试可用 dependency_overrides 注入桩）
    app.state.profile_writer = None
    if settings.effective_api_key:
        from lingyi.agent.graph import create_agent
        from lingyi.models.factory import create_llm
        from lingyi.parsers.file_parser import FileParser

        llm = create_llm(settings)
        app.state.agent, app.state.profile_writer = create_agent(
            llm=llm,
            rag_client=app.state.rag_client,
            storage=storage,
            safety_engine=app.state.safety_engine,
            file_parser=FileParser(),
            settings=settings,
        )
    else:
        logger.warning(
            "未配置 API Key，跳过 Agent 创建（认证接口返回 503；测试可用 dependency_overrides 注入）"
        )
        app.state.agent = None

    yield

    # flush 待完成的画像写入（ProfileWriterSkill 后台任务），再关闭持久连接
    if app.state.profile_writer is not None:
        await app.state.profile_writer.flush()
    await storage.close()
    logger.info("灵医 API 关闭")


def create_app() -> FastAPI:
    """
    创建 FastAPI 应用实例。

    Returns:
        配置好的 FastAPI 实例
    """
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
    from lingyi.api.routes import auth, chat, health, profiles, threads, upload

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(auth.router, prefix="/api", tags=["auth"])
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(threads.router, prefix="/api", tags=["threads"])
    app.include_router(profiles.router, prefix="/api", tags=["profiles"])
    app.include_router(upload.router, prefix="/api", tags=["upload"])

    return app


# 应用实例（uvicorn 直接引用: lingyi.api.app:app）
app = create_app()
