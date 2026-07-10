"""A-Stock Data MCP Server — standalone, zero tradingagents dependency.

Exposes 23 data tools (22 data functions + resolve_ticker) via FastMCP (stdio).
Compatible with Claude Code, OpenClaw, and Hermes.

Usage:
    # Start as stdio MCP server
    uv run python -m a_stock_mcp.server
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import sys
import threading
import time

from fastmcp import FastMCP

from a_stock_mcp.tools import register_tools

logger = logging.getLogger(__name__)

# Idle timeout (seconds): exit if no tool call for this duration.
# Configurable via MCP_IDLE_TIMEOUT env var; 0 = disabled.
_IDLE_TIMEOUT = int(os.environ.get("MCP_IDLE_TIMEOUT", "360"))

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

# Timestamp of the last tool call (updated by _idle_watchdog via call_tool hook)
_last_activity = time.time()


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
                logger.info("stdin EOF — MCP client disconnected, exiting")
                _cleanup_and_exit()
    except (OSError, ValueError):
        _cleanup_and_exit()


def _idle_watchdog():
    """Background thread: exit if no tool call within _IDLE_TIMEOUT seconds.

    Catches the case where the client doesn't close stdin but stops sending
    requests (e.g. session idle, client crash with pipe still open).
    """
    if _IDLE_TIMEOUT <= 0:
        return
    check_interval = 30  # check every 30s
    while True:
        time.sleep(check_interval)
        idle = time.time() - _last_activity
        if idle > _IDLE_TIMEOUT:
            logger.info("Idle for %ds (limit %ds) — exiting", int(idle), _IDLE_TIMEOUT)
            _cleanup_and_exit()


# Hook into FastMCP's call_tool to track last activity time
_original_call_tool = mcp.call_tool


async def _tracking_call_tool(*args, **kwargs):
    global _last_activity
    _last_activity = time.time()
    return await _original_call_tool(*args, **kwargs)


mcp.call_tool = _tracking_call_tool


def main():
    # Register cleanup hooks for common termination signals
    atexit.register(_cleanup_and_exit)
    signal.signal(signal.SIGTERM, _cleanup_and_exit)

    # Watch for stdin EOF (MCP client disconnect) in a daemon thread
    stdin_watcher = threading.Thread(target=_watch_stdin, daemon=True)
    stdin_watcher.start()

    # Watch for idle timeout (no tool calls for N seconds)
    idle_watcher = threading.Thread(target=_idle_watchdog, daemon=True)
    idle_watcher.start()

    mcp.run()


if __name__ == "__main__":
    main()
