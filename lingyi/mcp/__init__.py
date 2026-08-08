"""灵医 MCP 服务端 - 将 TCM 领域工具以 MCP (Model Context Protocol) 暴露给外部客户端。

这是 MCP 双向接入的 **expose 侧**：把灵医的本草查询、方剂检索、配伍安全校验、
经典检索、患者画像查询等能力包装为 MCP 工具，供 Claude Desktop 等外部客户端调用。
consume 侧（web_search 复用 RivalSearchMCP）见 ``lingyi/tools/web_search.py``。

启动方式（stdio 传输，Claude Desktop 标准协议）::

    python -m lingyi.mcp.server

详细实现见 ``lingyi/mcp/server.py``。
"""
