"""A-Stock Data MCP Server — standalone, zero tradingagents dependency.

Exposes 18 data tools (17 data functions + resolve_ticker) via FastMCP (stdio).
Compatible with Claude Code, OpenClaw, and Hermes.

Usage:
    # Start as stdio MCP server
    uv run python -m a_stock_mcp.server

    # Register with Claude Code:
    claude mcp add a-stock-data -- uv run --project D:/DevProject/TradingAgentTokenPlan/a-stock-mcp python -m a_stock_mcp.server
"""

from __future__ import annotations

import functools
import inspect

from a_stock_mcp.data import (
    get_stock_data as _get_stock_data,
    get_indicators as _get_indicators,
    get_fundamentals as _get_fundamentals,
    get_balance_sheet as _get_balance_sheet,
    get_cashflow as _get_cashflow,
    get_income_statement as _get_income_statement,
    get_news as _get_news,
    get_global_news as _get_global_news,
    get_insider_transactions as _get_insider_transactions,
    get_profit_forecast as _get_profit_forecast,
    get_hot_stocks as _get_hot_stocks,
    get_northbound_flow as _get_northbound_flow,
    get_concept_blocks as _get_concept_blocks,
    get_fund_flow as _get_fund_flow,
    get_dragon_tiger_board as _get_dragon_tiger_board,
    get_lockup_expiry as _get_lockup_expiry,
    get_industry_comparison as _get_industry_comparison,
    resolve_ticker as _resolve_ticker,
)

from fastmcp import FastMCP

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


# ---------------------------------------------------------------------------
# Utility: auto-coerce str params to prevent integer coercion by MCP framework
# ---------------------------------------------------------------------------


def _coerce_str_params(func):
    """Decorator: convert all str-typed params via str() before passing to func.

    Some MCP clients (e.g. OpenClaw) coerce pure-numeric strings like "600519"
    to integers. This decorator ensures every parameter declared as str receives
    an actual str value, regardless of what the caller sends.
    """
    sig = inspect.signature(func)
    str_params = {
        name
        for name, param in sig.parameters.items()
        if param.annotation is str or param.annotation == "str"
    }

    if not str_params:
        return func

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        for name in str_params:
            if name in bound.arguments and bound.arguments[name] is not None:
                bound.arguments[name] = str(bound.arguments[name])
        return func(*bound.args, **bound.kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


@mcp.tool()
@_coerce_str_params
def resolve_ticker(user_input: str) -> str:
    """Resolve a stock name or code to a 6-digit A-stock code.

    Accepts: '600379', 'SH600379', '600379.SH', '宝光股份'
    Returns the normalized 6-digit code (e.g. '600379').
    Use this when the user provides a Chinese stock name instead of a code.
    """
    return _resolve_ticker(user_input)


# ---------------------------------------------------------------------------
# Core Stock Data
# ---------------------------------------------------------------------------


@mcp.tool()
@_coerce_str_params
def get_stock_data(
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    """Retrieve stock price data (OHLCV) for a given A-stock code.

    Args:
        symbol: 6-digit A-stock code (e.g. 600379, 688017). NOT company name.
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.

    Returns:
        Formatted OHLCV data as a text table.
    """
    return _get_stock_data(symbol, start_date, end_date)


@mcp.tool()
@_coerce_str_params
def get_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """Retrieve technical indicators for a given A-stock code.

    Supported indicators (pass as the indicator parameter, one at a time):
    - close_50_sma, close_200_sma, close_10_ema (Moving Averages)
    - macd, macds, macdh (MACD)
    - rsi (RSI)
    - boll, boll_ub, boll_lb (Bollinger Bands)
    - atr (ATR)
    - vwma (Volume Weighted MA)

    Args:
        symbol: 6-digit A-stock code (e.g. 600379).
        indicator: Technical indicator identifier (e.g. 'rsi', 'macd').
        curr_date: Current trading date in YYYY-mm-dd format.
        look_back_days: How many days to look back (default 30).

    Returns:
        Formatted indicator data as a text table.
    """
    return _get_indicators(symbol, indicator, curr_date, look_back_days)


# ---------------------------------------------------------------------------
# Fundamental Data
# ---------------------------------------------------------------------------


@mcp.tool()
@_coerce_str_params
def get_fundamentals(
    ticker: str,
    curr_date: str | None = None,
) -> str:
    """Retrieve comprehensive fundamental data for a given A-stock code.

    Returns PE/PB, market cap, quarterly financial snapshots,
    consensus EPS, forward PE, PEG, and PE digestion time.

    Args:
        ticker: 6-digit A-stock code (e.g. 600379).
        curr_date: Current date in YYYY-mm-dd format (optional).

    Returns:
        Comprehensive fundamental report as text.
    """
    return _get_fundamentals(ticker, curr_date)


@mcp.tool()
@_coerce_str_params
def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    """Retrieve balance sheet data for a given A-stock code.

    Args:
        ticker: 6-digit A-stock code (e.g. 600379).
        freq: Reporting frequency: 'annual' or 'quarterly' (default quarterly).
        curr_date: Current date in YYYY-mm-dd format (optional).

    Returns:
        Balance sheet data as formatted text.
    """
    return _get_balance_sheet(ticker, freq, curr_date)


@mcp.tool()
@_coerce_str_params
def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    """Retrieve cash flow statement data for a given A-stock code.

    Args:
        ticker: 6-digit A-stock code (e.g. 600379).
        freq: Reporting frequency: 'annual' or 'quarterly' (default quarterly).
        curr_date: Current date in YYYY-mm-dd format (optional).

    Returns:
        Cash flow data as formatted text.
    """
    return _get_cashflow(ticker, freq, curr_date)


@mcp.tool()
@_coerce_str_params
def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    """Retrieve income statement data for a given A-stock code.

    Args:
        ticker: 6-digit A-stock code (e.g. 600379).
        freq: Reporting frequency: 'annual' or 'quarterly' (default quarterly).
        curr_date: Current date in YYYY-mm-dd format (optional).

    Returns:
        Income statement data as formatted text.
    """
    return _get_income_statement(ticker, freq, curr_date)


# ---------------------------------------------------------------------------
# News Data
# ---------------------------------------------------------------------------


@mcp.tool()
@_coerce_str_params
def get_news(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Retrieve stock-specific news for a given A-stock code.

    Args:
        ticker: 6-digit A-stock code (e.g. 600379).
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.

    Returns:
        News articles as formatted text.
    """
    return _get_news(ticker, start_date, end_date)


@mcp.tool()
@_coerce_str_params
def get_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 5,
) -> str:
    """Retrieve global financial news (CLS + Eastmoney).

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back (default 7).
        limit: Maximum number of articles to return (default 5).

    Returns:
        Global financial news articles as formatted text.
    """
    return _get_global_news(curr_date, look_back_days, limit)


@mcp.tool()
@_coerce_str_params
def get_insider_transactions(
    ticker: str,
) -> str:
    """Retrieve insider transaction / shareholder activity data.

    Uses mootdx F10 shareholder research data.

    Args:
        ticker: 6-digit A-stock code (e.g. 600379).

    Returns:
        Insider transaction data as formatted text.
    """
    return _get_insider_transactions(ticker)


# ---------------------------------------------------------------------------
# Signal Data (A-stock specific)
# ---------------------------------------------------------------------------


@mcp.tool()
@_coerce_str_params
def get_profit_forecast(
    ticker: str,
) -> str:
    """Retrieve consensus EPS forecasts with forward valuation metrics.

    Returns analyst coverage count, EPS range, forward PE, PEG,
    and PE digestion time from TongHuaShun (同花顺).

    Args:
        ticker: 6-digit A-stock code (e.g. 688017).

    Returns:
        Consensus forecast report with valuation metrics.
    """
    return _get_profit_forecast(ticker)


@mcp.tool()
@_coerce_str_params
def get_hot_stocks(
    curr_date: str = "",
) -> str:
    """Retrieve today's strong stocks with topic attribution reason tags.

    Shows WHY stocks surged (e.g. '算力租赁+AI政务'), curated by
    TongHuaShun editorial team. Includes theme frequency analysis.

    Args:
        curr_date: Date in YYYY-MM-DD format, empty string for today.

    Returns:
        Hot stocks list with reason tags and theme frequency.
    """
    return _get_hot_stocks(curr_date)


@mcp.tool()
@_coerce_str_params
def get_northbound_flow(
    curr_date: str,
    include_history: bool = False,
) -> str:
    """Retrieve northbound capital flow (沪深股通) data.

    Realtime: minute-level cumulative net buying for HGT + SGT.
    History (optional): daily-level data for trend analysis.

    Args:
        curr_date: Date in YYYY-MM-DD format.
        include_history: Include historical daily data (last 20 trading days).

    Returns:
        Northbound capital flow report.
    """
    return _get_northbound_flow(curr_date, include_history)


@mcp.tool()
@_coerce_str_params
def get_concept_blocks(
    ticker: str,
) -> str:
    """Retrieve concept/sector/region blocks that a stock belongs to.

    Shows industry (申万), concept themes (e.g. 机器人概念, 减速器),
    and region. Each block includes current day's change percentage.

    Args:
        ticker: 6-digit A-stock code (e.g. 688017).

    Returns:
        Concept and sector block membership with daily changes.
    """
    return _get_concept_blocks(ticker)


@mcp.tool()
@_coerce_str_params
def get_fund_flow(
    ticker: str,
    curr_date: str,
    include_history: bool = True,
) -> str:
    """Retrieve individual stock fund flow (main force vs retail).

    Realtime: minute-level super/large/medium/small order flow.
    History: daily net inflow by order size for 20 trading days.

    Args:
        ticker: 6-digit A-stock code.
        curr_date: Date in YYYY-MM-DD format.
        include_history: Include 20-day historical daily flow (default True).

    Returns:
        Fund flow report with main force signal.
    """
    return _get_fund_flow(ticker, curr_date, include_history)


@mcp.tool()
@_coerce_str_params
def get_dragon_tiger_board(
    ticker: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """Retrieve dragon-tiger board (龙虎榜) data for a stock.

    Shows recent LHB appearances, top buyer/seller seats (营业部),
    and institutional involvement. Key signal for hot money tracking.

    Args:
        ticker: 6-digit A-stock code (e.g. 000858).
        curr_date: Date in YYYY-MM-DD format.
        look_back_days: Days to look back (default 30).

    Returns:
        LHB appearances with seat details and institutional activity.
    """
    return _get_dragon_tiger_board(ticker, curr_date, look_back_days)


@mcp.tool()
@_coerce_str_params
def get_lockup_expiry(
    ticker: str,
    curr_date: str,
    forward_days: int = 90,
) -> str:
    """Retrieve lockup expiry (限售解禁) schedule for a stock.

    Shows historical unlock records and upcoming expiry calendar
    with impact metrics (unlock quantity, market cap ratio).

    Args:
        ticker: 6-digit A-stock code (e.g. 000858).
        curr_date: Date in YYYY-MM-DD format.
        forward_days: Days forward to check (default 90).

    Returns:
        Lockup expiry schedule with impact assessment.
    """
    return _get_lockup_expiry(ticker, curr_date, forward_days)


@mcp.tool()
@_coerce_str_params
def get_industry_comparison(
    ticker: str,
    curr_date: str,
) -> str:
    """Retrieve industry sector performance comparison (行业横向对比).

    Shows all 90 THS industries ranked by performance with turnover,
    net capital flow, and leading stocks.

    Args:
        ticker: 6-digit A-stock code (used to identify relevant sector).
        curr_date: Date in YYYY-MM-DD format.

    Returns:
        Industry performance ranking with key metrics.
    """
    return _get_industry_comparison(ticker, curr_date)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
