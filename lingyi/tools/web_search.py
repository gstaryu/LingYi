"""
web_search 工具 - 复用 RivalSearchMCP 服务（langchain-mcp-adapters stdio 传输）。

设计要点:
- 通过 MultiServerMCPClient 以 stdio 方式拉起 RivalSearchMCP 子进程，加载其 9 个工具中的
  ``web_search``，再用 StructuredTool 包装成统一的 ``web_search(query: str) -> list[dict]`` 接口。
- MCP 客户端是有状态的（持有子进程），build_web_search_tool 返回的 BaseTool 闭包持有该客户端，
  保证工具存活期间子进程常驻；客户端引用同时挂在 tool.mcp_client 上便于显式关闭。
- 连接/调用失败时按 ``web_search_fallback_to_ddgs`` 配置决定回退 DuckDuckGo 或优雅返回 None
  （None 时 create_tools 会省略 web_search，Agent 仍可正常运行）。
- 参考 dive-into-langgraph 第 7/11 章：官方 MultiServerMCPClient + get_tools() 模式，不造轮子。
"""

import asyncio
import logging
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from lingyi.tools.schemas import WebSearchInput

logger = logging.getLogger(__name__)

# MCP 连接/调用超时（秒）——RivalSearchMCP 含 scrapling/playwright 类型导入，冷启动需留余量
_MCP_CONNECT_TIMEOUT = 90
_MCP_CALL_TIMEOUT = 60


def _normalize_search_results(result: Any) -> list[dict]:
    """
    将 MCP / DDGS 的异构返回归一化为 JSON 可序列化的 list[dict]。

    MCP web_search 返回 LangChain 内容块列表 [{"type": "text", "text": "..."}]；
    DDGS DuckDuckGoSearchRun 返回 str。统一输出 [{"content": str}, ...]。
    """
    if isinstance(result, str):
        return [{"content": result}] if result else [{"content": "无搜索结果"}]
    if isinstance(result, list):
        out: list[dict] = []
        for item in result:
            if isinstance(item, dict):
                if "text" in item:
                    out.append({"content": item["text"]})
                else:
                    out.append(item)
            elif isinstance(item, str):
                out.append({"content": item})
        return out or [{"content": "无搜索结果"}]
    if isinstance(result, dict):
        return [result]
    return [{"content": str(result)}]


def _make_mcp_web_search_tool(mcp_tool: BaseTool, client: Any) -> BaseTool:
    """将 MCP web_search 包装为统一的 (query: str) -> list[dict] StructuredTool。"""

    async def _web_search(query: str) -> list[dict]:
        try:
            # 关闭重内容抽取与链接跟随，仅取摘要，降低延迟与 payload 体积
            res = await asyncio.wait_for(
                mcp_tool.ainvoke(
                    {
                        "query": query,
                        "extract_content": False,
                        "follow_links": False,
                        "num_results": 5,
                    }
                ),
                timeout=_MCP_CALL_TIMEOUT,
            )
            return _normalize_search_results(res)
        except asyncio.TimeoutError:
            logger.warning("web_search(MCP) 调用超时: query=%s", query)
            return [{"error": "web_search 调用超时"}]
        except Exception as e:  # noqa: BLE001 - 工具层需吞异常返回结构化错误，避免击穿 Agent
            logger.warning("web_search(MCP) 调用异常: %s", e)
            return [{"error": f"web_search 调用失败: {e}"}]

    tool = StructuredTool.from_function(
        coroutine=_web_search,
        name="web_search",
        description=(
            "搜索互联网获取最新信息（多引擎：DuckDuckGo/Bing/Yahoo/Wikipedia）。"
            "用于补充中医领域之外的现代医学、新闻、科研等实时信息。返回搜索结果文本列表。"
        ),
        args_schema=WebSearchInput,
    )
    # 持有 MCP 客户端引用，避免子进程被 GC；同时暴露给上层做显式关闭。
    # StructuredTool 是 Pydantic v2 模型，普通赋值会拒绝未知字段，用 object.__setattr__ 绕过。
    try:
        object.__setattr__(tool, "mcp_client", client)
    except Exception:  # noqa: BLE001 - 仅尽力附加，失败不影响工具可用性
        logger.debug("无法附加 mcp_client 属性到 StructuredTool（不影响功能）")
    return tool


def _make_ddgs_web_search_tool() -> BaseTool | None:
    """DuckDuckGo 回退工具；ddgs/langchain-community 不可用时返回 None。"""
    try:
        from langchain_community.tools import DuckDuckGoSearchRun
    except Exception as e:  # noqa: BLE001
        logger.warning("DuckDuckGo 回退不可用（langchain-community 缺失）: %s", e)
        return None

    ddgs = DuckDuckGoSearchRun()

    async def _web_search(query: str) -> list[dict]:
        try:
            # DuckDuckGoSearchRun.invoke 是同步阻塞调用，放线程池避免阻塞事件循环
            res = await asyncio.to_thread(ddgs.invoke, {"query": query})
            return _normalize_search_results(res)
        except Exception as e:  # noqa: BLE001
            logger.warning("web_search(DDGS) 调用异常: %s", e)
            return [{"error": f"web_search 调用失败: {e}"}]

    return StructuredTool.from_function(
        coroutine=_web_search,
        name="web_search",
        description=(
            "搜索互联网获取最新信息（DuckDuckGo 引擎）。"
            "用于补充中医领域之外的现代医学、新闻、科研等实时信息。返回搜索结果文本列表。"
        ),
        args_schema=WebSearchInput,
    )


async def _safe_close_client(client: Any) -> None:
    """尽力关闭 MCP 客户端子进程，忽略错误。"""
    close = getattr(client, "close", None)
    if close is None:
        close = getattr(client, "aclose", None)
    if close is None:
        return
    try:
        if asyncio.iscoroutinefunction(close):
            await close()
        else:
            close()
    except Exception as e:  # noqa: BLE001
        logger.debug("关闭 MCP 客户端时忽略异常: %s", e)


async def build_web_search_tool(settings: Any) -> BaseTool | None:
    """
    构造 web_search 工具。

    优先复用 RivalSearchMCP（stdio 子进程 + langchain-mcp-adapters）。
    - settings.web_search_enabled=False -> 直接返回 None。
    - MCP 连接成功 -> 返回包装后的 web_search StructuredTool（持有客户端引用）。
    - MCP 连接失败且 web_search_fallback_to_ddgs=True -> 回退 DuckDuckGo（需 ddgs 包）。
    - MCP 连接失败且 fallback=False -> 返回 None（create_tools 将省略该工具）。

    Args:
        settings: lingyi.config.Settings 实例（或鸭子类型对象，含下列字段）。

    Returns:
        BaseTool 或 None。
    """
    if not getattr(settings, "web_search_enabled", True):
        logger.info("web_search 已通过配置禁用，省略该工具")
        return None

    command = getattr(
        settings,
        "rivalsearch_mcp_command",
        "C:/Users/start/mcp-servers/RivalSearchMCP/.venv/Scripts/python.exe",
    )
    script = getattr(
        settings,
        "rivalsearch_mcp_script",
        "C:/Users/start/mcp-servers/RivalSearchMCP/server.py",
    )
    fallback_to_ddgs = getattr(settings, "web_search_fallback_to_ddgs", False)

    # ---- 1) 尝试 MCP stdio 复用 ----
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(
            {
                "rivalsearch": {
                    "command": command,
                    "args": [script],
                    "transport": "stdio",
                }
            }
        )
        try:
            tools = await asyncio.wait_for(client.get_tools(), timeout=_MCP_CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("RivalSearchMCP 连接超时（%ds）", _MCP_CONNECT_TIMEOUT)
            await _safe_close_client(client)
            tools = []
        except Exception as e:  # noqa: BLE001 - 连接失败进入回退逻辑
            logger.warning("RivalSearchMCP 连接失败: %s", e)
            await _safe_close_client(client)
            tools = []

        mcp_web_search = next((t for t in tools if t.name == "web_search"), None)
        if mcp_web_search is not None:
            logger.info("web_search 工具已通过 RivalSearchMCP(stdio) 加载")
            return _make_mcp_web_search_tool(mcp_web_search, client)
        # 未找到 web_search 工具，清理已建立的子进程连接
        await _safe_close_client(client)
        logger.warning("RivalSearchMCP 已连接但未暴露 web_search 工具")
    except Exception as e:  # noqa: BLE001 - 适配器缺失等
        logger.warning("加载 langchain-mcp-adapters 失败，将尝试回退: %s", e)

    # ---- 2) 回退 DuckDuckGo 或优雅返回 None ----
    if fallback_to_ddgs:
        tool = _make_ddgs_web_search_tool()
        if tool is not None:
            logger.info("web_search 工具已回退到 DuckDuckGo")
            return tool
        logger.warning("DuckDuckGo 回退不可用（未安装 ddgs / langchain-community）")

    logger.info("web_search 工具未启用（MCP 不可用且未启用 DDGS 回退），Agent 将省略该工具")
    return None
