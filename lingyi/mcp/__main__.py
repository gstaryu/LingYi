"""``python -m lingyi.mcp`` 入口 - 等价于 ``python -m lingyi.mcp.server``。

启动 stdio MCP 服务（Claude Desktop 标准协议）。主逻辑见 ``server.py``。
"""

from lingyi.mcp.server import main

if __name__ == "__main__":
    main()
