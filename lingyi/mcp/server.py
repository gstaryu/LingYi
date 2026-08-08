"""
灵医 MCP 服务端 - 以 FastMCP (stdio) 暴露 TCM 领域工具。

设计要点（参考 dive-into-langgraph 第 7 章 + 适配已安装 mcp SDK v1.29.0）:
- 使用 ``mcp.server.fastmcp.FastMCP``（注意：ch7 用的是独立 ``fastmcp`` 包，路径不同；
  且 ch7 用 ``asyncio.run(mcp.run())`` 包装，而本版本 ``mcp.run()`` 是同步方法、内部自建事件循环，
  因此直接 ``mcp.run(transport="stdio")`` 调用，不再包 ``asyncio.run``）。
- 工具用 ``@mcp.tool()`` 装饰（带括号）。装饰器返回原函数，故测试可直接 ``await lookup_herb(...)``。
- 依赖注入通过模块级 ``_deps`` 持有者 + ``configure()``：
  - 生产：``app_lifespan`` 在服务事件循环内初始化 SQLiteStorage/SafetyEngine/RAGClient 并写入 ``_deps``
    （aiosqlite 连接绑定到事件循环，必须在 server loop 内创建，故用 lifespan 而非 ``asyncio.run`` 预初始化）。
  - 测试：直接 ``configure(...)`` 注入桩依赖，跳过 lifespan，按函数调用工具。
- 只读安全：仅暴露查询/校验类工具，不暴露 ``save_patient_profile``（避免外部客户端写库风险）。
- 知识库未 seed 时优雅降级：返回空/``{"error":"未找到"}``，不崩溃。
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


# ==================== 依赖持有者 ====================


@dataclass
class _Deps:
    """MCP 工具的运行时依赖（由 lifespan 或测试 configure 注入）。

    所有字段在工具调用时才读取，故可在注册后任意替换（测试友好）。
    """

    storage: Any = None
    safety_engine: Any = None
    rag_client: Any = None


_deps = _Deps()


def configure(
    storage: Any = None,
    safety_engine: Any = None,
    rag_client: Any = None,
) -> None:
    """注入/替换 MCP 工具依赖。

    供 ``app_lifespan``（生产）与测试共用：写入模块级 ``_deps``，工具函数调用时读取。
    传入 ``None`` 的字段保持不变（便于测试只替换部分依赖）。
    """
    if storage is not None:
        _deps.storage = storage
    if safety_engine is not None:
        _deps.safety_engine = safety_engine
    if rag_client is not None:
        _deps.rag_client = rag_client


# ==================== 数据转换（镜像 tools/factory.py，保持解耦）====================


def _herb_to_dict(herb: Any) -> dict:
    """Herb dataclass -> LLM 友好 dict。"""
    return {
        "name": herb.name,
        "aliases": list(herb.aliases),
        "nature_flavor": herb.nature_flavor,
        "meridians": list(herb.meridians),
        "efficacy": herb.efficacy,
        "indications": list(herb.indications),
        "dosage": herb.dosage,
        "processing": herb.processing,
        "contraindications": herb.contraindications,
    }


def _formula_to_dict(formula: Any) -> dict:
    """Formula dataclass -> dict（仅暴露 name/source/composition/indication）。"""
    return {
        "name": formula.name,
        "source": formula.source,
        "composition": [
            {"herb": c.herb, "dosage": c.dosage} for c in formula.composition
        ],
        "indication": formula.indication,
    }


def _profile_to_dict(profile: Any) -> dict:
    """UserProfile -> dict（体质/过敏/既往史）。"""
    return {
        "patient_id": profile.patient_id,
        "constitution": profile.constitution,
        "allergies": profile.allergies,
        "past_history": list(profile.past_history),
    }


# ==================== RAG 客户端工厂（镜像 api/app.py._create_rag_client）====================


def _create_rag_client(settings: Any) -> Any:
    """根据配置创建 RAG 客户端（mock/chroma）。

    与 ``lingyi.api.app._create_rag_client`` 保持一致：mock 模式无外部依赖，
    chroma 模式延迟加载 embedding 模型。
    """
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


# ==================== 服务生命周期 ====================


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """FastMCP lifespan：在服务事件循环内初始化依赖并写入 ``_deps``。

    必须在 lifespan 内创建 SQLiteStorage：aiosqlite 连接绑定创建时的事件循环，
    而 ``mcp.run()`` 自建独立事件循环——若在 ``asyncio.run()`` 预初始化后再 ``mcp.run()``，
    连接会绑定到已销毁的循环导致跨循环报错。

    Yields:
        依赖字典（亦可通过 MCP Context.get_lifespan() 访问，但本实现工具直接读 ``_deps``）。
    """
    from lingyi.config import get_settings
    from lingyi.safety.rules import SafetyEngine
    from lingyi.storage.sqlite import SQLiteStorage

    settings = get_settings()
    logger.info(
        "灵医 MCP 服务启动中... RAG 模式: %s, DB: %s", settings.rag_mode, settings.db_path
    )

    storage = SQLiteStorage(settings.db_path)
    await storage.init_db()

    safety_engine = SafetyEngine()
    rag_client = _create_rag_client(settings)

    # 知识库 seed 检查（不自动写入，仅提示）
    try:
        sample = await storage.get_herb("甘草")
        if sample is None:
            logger.warning(
                "知识库 herbs 表似乎为空，建议先运行 "
                "`python -m data_pipeline.seed_knowledge` 灌入本草/方剂/禁忌种子数据。"
            )
    except Exception as e:  # noqa: BLE001 - seed 检查失败不应阻断启动
        logger.warning("检查知识库种子失败: %s", e)

    configure(storage=storage, safety_engine=safety_engine, rag_client=rag_client)
    logger.info("灵医 MCP 依赖初始化完成，工具已就绪")

    try:
        yield {
            "storage": storage,
            "safety_engine": safety_engine,
            "rag_client": rag_client,
        }
    finally:
        try:
            await storage.close()
        except Exception as e:  # noqa: BLE001 - 关闭失败仅记录
            logger.warning("关闭 SQLiteStorage 失败: %s", e)
        logger.info("灵医 MCP 服务已关闭")


# ==================== FastMCP 实例 ====================

mcp = FastMCP("lingyi-tcm", lifespan=app_lifespan)


# ==================== MCP 工具（只读：查询/校验类）====================


@mcp.tool()
async def search_tcm_classics(query: str) -> list[str]:
    """检索中医经典古籍（伤寒论/金匮要略等）中与查询相关的条文。

    Args:
        query: 检索关键词或证候描述，例如 "太阳病中风" 或 "桂枝汤证"

    Returns:
        相关古籍条文的文本列表（按相关性降序）；无结果或服务未初始化时返回空列表。
    """
    rag = _deps.rag_client
    if rag is None:
        logger.warning("search_tcm_classics 调用时 RAG 客户端未初始化")
        return []
    results = await rag.hybrid_search(query, n_results=8)
    return [r.content for r in results]


@mcp.tool()
async def lookup_herb(name: str) -> dict:
    """按药材正名精确查询本草信息（性味、归经、功效、主治、用量、禁忌）。

    Args:
        name: 药材正名，例如 "人参"、"黄芪"、"甘草"

    Returns:
        本草信息字典；未找到时返回 {"error": "未找到"}；服务未初始化时返回 {"error": "服务未初始化"}。
    """
    storage = _deps.storage
    if storage is None:
        return {"error": "服务未初始化"}
    herb = await storage.get_herb(name)
    if herb is None:
        return {"error": "未找到"}
    return _herb_to_dict(herb)


@mcp.tool()
async def search_formulas(query: str) -> list[dict]:
    """按证候或关键词搜索方剂，返回方剂列表（名称、出处、组成、主治）。

    Args:
        query: 证候或关键词，例如 "太阳中风" 或 "桂枝汤"

    Returns:
        方剂字典列表；无结果或服务未初始化时返回空列表。
    """
    storage = _deps.storage
    if storage is None:
        return []
    formulas = await storage.search_formulas(query)
    return [_formula_to_dict(f) for f in formulas]


@mcp.tool()
async def check_herb_safety(herbs: list[str]) -> dict:
    """校验药方配伍安全：检查十八反/十九畏配伍禁忌。

    Args:
        herbs: 药材名称列表，例如 ["甘草", "甘遂"]

    Returns:
        {"safe": bool, "violations": list[str], "warnings": list[str]}。
        safe=False 时 violations 非空。
    """
    safety = _deps.safety_engine
    if safety is None:
        return {
            "safe": True,
            "violations": [],
            "warnings": [],
            "error": "安全引擎未初始化",
        }

    # 十八反/十九畏 配伍禁忌（SafetyEngine 物理规则引擎）
    is_safe, error_msg = safety.check_prescription(herbs)
    if is_safe:
        violations: list[str] = []
    else:
        # SafetyEngine 用 '；' 连接多条冲突，拆分还原为列表
        violations = [v for v in (error_msg or "").split("；") if v]

    return {"safe": is_safe, "violations": violations, "warnings": []}


@mcp.tool()
async def get_patient_profile(patient_id: str) -> dict:
    """获取患者画像（体质类型、过敏史、既往诊疗记录）。

    Args:
        patient_id: 患者 ID（通常等于 username）

    Returns:
        患者画像字典；不存在时返回默认画像（体质=未知、过敏=无）；
        服务未初始化时返回 {"error": "服务未初始化"}。
    """
    storage = _deps.storage
    if storage is None:
        return {"error": "服务未初始化"}
    profile = await storage.get_profile(patient_id)
    return _profile_to_dict(profile)


# ==================== 入口 ====================


def main() -> None:
    """启动 MCP 服务（stdio 传输，Claude Desktop 标准协议）。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("启动灵医 MCP 服务（stdio）...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
