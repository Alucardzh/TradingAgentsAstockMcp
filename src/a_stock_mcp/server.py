"""A-Stock Data MCP Server — standalone, zero tradingagents dependency.

Exposes 19 data tools (18 data functions + resolve_ticker) via FastMCP (stdio).
Compatible with Claude Code, OpenClaw, and Hermes.

Usage:
    # Start as stdio MCP server
    uv run python -m a_stock_mcp.server
"""

from __future__ import annotations

from fastmcp import FastMCP

from a_stock_mcp.tools import register_tools

mcp = FastMCP(
    "a-stock-data",
    instructions=(
        "A-share (China mainland) stock data service. "
        "All ticker parameters accept 6-digit codes (e.g. 600379, 688017). "
        "Chinese stock names are also accepted via resolve_ticker. "
        "Eastmoney requests are rate-limited (1s minimum interval). "
        "All data is for research purposes only, not investment advice."
    ),
)

# Register all 19 tools (wrappers with MCP-facing docstrings + str coercion)
register_tools(mcp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
