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
from lingyi.tracing import setup_tracing

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


def _create_reranker(settings):
    """根据配置创建重排器（mock 模式用 MockReranker，chroma 模式用 CrossEncoderReranker 延迟加载）。"""
    if settings.rag_mode == "chroma":
        from lingyi.rag.reranker import CrossEncoderReranker

        return CrossEncoderReranker(model_name=settings.rerank_model_name)
    from lingyi.rag.reranker import MockReranker

    return MockReranker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动创建实例并存入 app.state，关闭释放连接。"""
    settings = get_settings()
    setup_logging(settings.log_level)
    setup_tracing(settings)
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

    # reranker（精排；chroma 模式延迟加载 CrossEncoder，mock 模式用 MockReranker）
    app.state.reranker = _create_reranker(settings)

    # checkpointer（LangGraph 状态持久化，与业务库分离；由 lifespan 统一创建与关闭）
    from lingyi.storage.checkpointer import close_checkpointer, create_checkpointer

    app.state.checkpointer = create_checkpointer(settings.checkpoints_db_path)

    # agent（需 LLM；未配置 API Key 时跳过，测试可用 dependency_overrides 注入桩）
    app.state.profile_writer = None
    app.state.tools = None
    app.state.web_search_tool = None
    if settings.effective_api_key:
        from lingyi.models.factory import create_llm
        from lingyi.parsers.file_parser import FileParser
        from lingyi.tools.factory import create_tools
        from lingyi.tools.web_search import build_web_search_tool

        llm = create_llm(settings)
        file_parser = FileParser()

        # 构建 web_search 工具（可选，MCP 不可用时返回 None）
        web_search_tool = await build_web_search_tool(settings)
        app.state.web_search_tool = web_search_tool

        # 构建完整工具集（create_tools 根据 web_search_client 是否为 None 决定附加）
        tools = create_tools(
            rag_client=app.state.rag_client,
            storage=storage,
            safety_engine=app.state.safety_engine,
            web_search_client=web_search_tool,
        )
        app.state.tools = tools

        # AGENT_MODE 切换: workflow（默认单 Agent）/ multiagent（多智能体会诊）
        if settings.agent_mode == "multiagent":
            from lingyi.agent.graph_multiagent import create_multiagent_agent

            app.state.agent, app.state.profile_writer = create_multiagent_agent(
                llm=llm,
                rag_client=app.state.rag_client,
                storage=storage,
                safety_engine=app.state.safety_engine,
                checkpointer=app.state.checkpointer,
                tools=tools,
                web_search_tool=web_search_tool,
                settings=settings,
                file_parser=file_parser,
            )
            logger.info("Agent 模式: multiagent（多智能体会诊）")
        else:
            from lingyi.agent.graph import create_agent

            app.state.agent, app.state.profile_writer = create_agent(
                llm=llm,
                rag_client=app.state.rag_client,
                storage=storage,
                safety_engine=app.state.safety_engine,
                checkpointer=app.state.checkpointer,
                reranker=app.state.reranker,
                file_parser=file_parser,
                settings=settings,
            )
            logger.info("Agent 模式: workflow（单 Agent 工作流）")
    else:
        logger.warning(
            "未配置 API Key，跳过 Agent 创建（认证接口返回 503；测试可用 dependency_overrides 注入）"
        )
        app.state.agent = None

    yield

    # flush 待完成的画像写入（ProfileWriterSkill 后台任务），再关闭持久连接
    if app.state.profile_writer is not None:
        await app.state.profile_writer.flush()
    # 关闭 web_search MCP 子进程（如有）
    web_search_tool = getattr(app.state, "web_search_tool", None)
    if web_search_tool is not None:
        from lingyi.tools.web_search import _safe_close_client

        mcp_client = getattr(web_search_tool, "mcp_client", None)
        if mcp_client is not None:
            await _safe_close_client(mcp_client)
    await close_checkpointer(app.state.checkpointer)
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

    # CORS 配置（白名单，避免 allow_origins=* 与 allow_credentials=True 冲突）
    settings = get_settings()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
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
