"""
灵医 Agent 工具层。

领域工具集通过 create_tools(rag_client, storage, safety_engine, web_search_client) 构造，
依赖注入、闭包捕获，不持有模块级全局单例（镜像 graph.py DI 风格）。

- create_tools: 构建 6 个闭包工具 + 可选 web_search。
- build_web_search_tool: 异步构造 web_search 工具（复用 RivalSearchMCP，失败可回退 DDGS）。
"""

from lingyi.tools.factory import create_tools
from lingyi.tools.web_search import build_web_search_tool

__all__ = ["create_tools", "build_web_search_tool"]
