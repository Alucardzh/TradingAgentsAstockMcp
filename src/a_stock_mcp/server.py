"""A-Stock Data MCP Server — standalone, zero tradingagents dependency.

Exposes 23 data tools (22 data functions + resolve_ticker) via FastMCP (stdio).
Compatible with Claude Code, OpenClaw, and Hermes.

Usage:
    # Start as stdio MCP server
    uv run python -m a_stock_mcp.server
"""

from __future__ import annotations

import atexit
import os
import signal
import sys
import threading

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

# Register all 23 tools (wrappers with MCP-facing docstrings + str coercion)
register_tools(mcp)


def _cleanup_and_exit(signum=None, frame=None):
    """Force-exit the process, ensuring no lingering threads/sessions."""
    os._exit(0)


def _watch_stdin():
    """Background thread: exit when MCP client disconnects (stdin EOF).

    Some MCP clients (e.g. OpenClaw) don't send a proper shutdown — they just
    close the pipe. Without this watcher the process lingers as a zombie because
    mcp.run() blocks on its event loop while non-daemon threads (requests
    Keep-Alive, curl_cffi) keep the process alive.
    """
    try:
        while True:
            data = sys.stdin.buffer.read(1)
            if not data:
                # stdin closed (EOF) — client gone
                _cleanup_and_exit()
    except (OSError, ValueError):
        _cleanup_and_exit()


def main():
    # Register cleanup hooks for common termination signals
    atexit.register(_cleanup_and_exit)
    signal.signal(signal.SIGTERM, _cleanup_and_exit)

    # Watch for stdin EOF (MCP client disconnect) in a daemon thread
    watcher = threading.Thread(target=_watch_stdin, daemon=True)
    watcher.start()

    mcp.run()


if __name__ == "__main__":
    main()
