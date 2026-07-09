"""A-stock MCP tool functions, grouped by domain.

Import the raw functions directly:
    ``from a_stock_mcp.tools import get_stock_data``

Or register all 23 tools onto a FastMCP instance:
    ``from a_stock_mcp.tools import register_tools``
    ``register_tools(mcp)``
"""

from __future__ import annotations

import functools
import inspect

from a_stock_mcp._core import resolve_ticker as _resolve_ticker
from a_stock_mcp.tools.capital import (
    get_dragon_tiger_board as _get_dragon_tiger_board,
)
from a_stock_mcp.tools.capital import (
    get_fund_flow as _get_fund_flow,
)
from a_stock_mcp.tools.capital import (
    get_northbound_flow as _get_northbound_flow,
)
from a_stock_mcp.tools.fundamentals import (
    get_balance_sheet as _get_balance_sheet,
)
from a_stock_mcp.tools.fundamentals import (
    get_cashflow as _get_cashflow,
)
from a_stock_mcp.tools.fundamentals import (
    get_fundamentals as _get_fundamentals,
)
from a_stock_mcp.tools.fundamentals import (
    get_income_statement as _get_income_statement,
)
from a_stock_mcp.tools.fundamentals import (
    get_profit_forecast as _get_profit_forecast,
)
from a_stock_mcp.tools.market import (
    calculate_support_resistance as _calculate_support_resistance,
)
from a_stock_mcp.tools.market import (
    get_indicators as _get_indicators,
)
from a_stock_mcp.tools.market import (
    get_market_index as _get_market_index,
)
from a_stock_mcp.tools.market import (
    get_stock_data as _get_stock_data,
)
from a_stock_mcp.tools.market import (
    get_stock_realtime as _get_stock_realtime,
)
from a_stock_mcp.tools.news import (
    get_global_news as _get_global_news,
)
from a_stock_mcp.tools.news import (
    get_news as _get_news,
)
from a_stock_mcp.tools.screening import (
    get_company_announcements as _get_company_announcements,
)
from a_stock_mcp.tools.screening import (
    get_concept_blocks as _get_concept_blocks,
)
from a_stock_mcp.tools.screening import (
    get_hot_stocks as _get_hot_stocks,
)
from a_stock_mcp.tools.screening import (
    get_industry_comparison as _get_industry_comparison,
)
from a_stock_mcp.tools.screening import (
    get_ths_hot_list as _get_ths_hot_list,
)
from a_stock_mcp.tools.shareholder import (
    get_insider_transactions as _get_insider_transactions,
)
from a_stock_mcp.tools.shareholder import (
    get_lockup_expiry as _get_lockup_expiry,
)

__all__ = [
    "register_tools",
    # market
    "get_stock_data",
    "get_indicators",
    "calculate_support_resistance",
    "get_market_index",
    "get_stock_realtime",
    # fundamentals
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_profit_forecast",
    # news
    "get_news",
    "get_global_news",
    # capital
    "get_fund_flow",
    "get_northbound_flow",
    "get_dragon_tiger_board",
    # shareholder
    "get_insider_transactions",
    "get_lockup_expiry",
    # screening
    "get_hot_stocks",
    "get_concept_blocks",
    "get_company_announcements",
    "get_industry_comparison",
    "get_ths_hot_list",
]

# Re-export the un-aliased names so ``from a_stock_mcp.tools import get_stock_data`` works
from a_stock_mcp.tools.capital import get_dragon_tiger_board, get_fund_flow, get_northbound_flow  # noqa: E402
from a_stock_mcp.tools.fundamentals import (  # noqa: E402
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_profit_forecast,
)
from a_stock_mcp.tools.market import (  # noqa: E402
    calculate_support_resistance,
    get_indicators,
    get_market_index,
    get_stock_data,
    get_stock_realtime,
)
from a_stock_mcp.tools.news import get_global_news, get_news  # noqa: E402
from a_stock_mcp.tools.screening import (  # noqa: E402
    get_company_announcements,
    get_concept_blocks,
    get_hot_stocks,
    get_industry_comparison,
    get_ths_hot_list,
)
from a_stock_mcp.tools.shareholder import get_insider_transactions, get_lockup_expiry  # noqa: E402

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
        name for name, param in sig.parameters.items() if param.annotation is str or param.annotation == "str"
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
# Tool registration — wraps raw functions with MCP-facing docstrings + coercion
# ---------------------------------------------------------------------------


def register_tools(mcp) -> None:
    """Register all 23 A-stock tools onto a FastMCP instance.

    Each tool is a thin wrapper with an MCP-consumer-facing docstring and
    ``_coerce_str_params`` applied, then registered via ``@mcp.tool()``.
    Wrappers use the same name as the public tool (e.g. ``get_stock_data``);
    raw implementations are imported with ``_``-prefixed aliases to avoid clashes.
    """

    # --- Utility ---

    @mcp.tool()
    @_coerce_str_params
    def resolve_ticker(user_input: str) -> str:
        """Resolve a stock name or code to a 6-digit A-stock code.

        Accepts: '600379', 'SH600379', '600379.SH', '宝光股份'
        Returns the normalized 6-digit code (e.g. '600379').
        Use this when the user provides a Chinese stock name instead of a code.
        """
        return _resolve_ticker(user_input)

    # --- Market Data ---

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

        Supported indicators (pass as the indicator parameter, one at a time, or 'all'):
        - close_50_sma, close_200_sma, close_10_ema (Moving Averages)
        - macd, macds, macdh (MACD)
        - rsi (RSI)
        - boll, boll_ub, boll_lb (Bollinger Bands)
        - atr (ATR)
        - vwma (Volume Weighted MA)
        - mfi (Money Flow Index)
        - all (all of the above)

        Args:
            symbol: 6-digit A-stock code (e.g. 600379).
            indicator: Technical indicator identifier (e.g. 'rsi', 'macd', 'all').
            curr_date: Current trading date in YYYY-mm-dd format.
            look_back_days: How many days to look back (default 30).

        Returns:
            Formatted indicator data as a text table.
        """
        return _get_indicators(symbol, indicator, curr_date, look_back_days)

    @mcp.tool()
    @_coerce_str_params
    def calculate_support_resistance(
        symbol: str,
        curr_date: str,
        n_levels: int = 5,
        lookback_period: int = 60,
    ) -> str:
        """Calculate support and resistance levels from historical price distribution.

        Uses a histogram-based algorithm to find price zones where the stock
        spent the most time, then clusters nearby levels. Supports are in the
        bottom 40% of the range, resistances in the top 40%.

        Args:
            symbol: 6-digit A-stock code (e.g. 600519).
            curr_date: Current date YYYY-MM-DD (prevents look-ahead bias).
            n_levels: Number of levels per side (1-10, default 5).
            lookback_period: Analysis window in days (30-365, default 60).

        Returns:
            Support/resistance levels with distance from current price,
            annualized volatility, and price trend.
        """
        return _calculate_support_resistance(symbol, curr_date, n_levels, lookback_period)

    @mcp.tool()
    @_coerce_str_params
    def get_market_index(
        index_code: str = "000001",
    ) -> str:
        """Get real-time market index snapshot (上证指数/沪深300/创业板指 etc.).

        Supports: 000001(上证), 000300(沪深300), 000016(上证50),
        399006(创业板指), 000688(科创50), 000905(中证500).

        Args:
            index_code: 6-digit index code (default 000001 for Shanghai Composite).

        Returns:
            Index snapshot: current point, change, volume, amount.
        """
        return _get_market_index(index_code)

    @mcp.tool()
    @_coerce_str_params
    def get_stock_realtime(
        symbol: str,
    ) -> str:
        """Get real-time stock price snapshot (current price, change, volume).

        Lightweight single-stock quote. Faster than get_stock_data (historical
        K-lines) when you only need the latest tick.

        Args:
            symbol: 6-digit A-stock code (e.g. 600519).

        Returns:
            Realtime price, change, volume, amount, high/low, turnover rate.
        """
        return _get_stock_realtime(symbol)

    # --- Fundamental Data ---

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
            curr_date: Current date in YYYY-MM-DD format (optional).

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
            curr_date: Current date in YYYY-MM-DD format (optional).

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
            curr_date: Current date in YYYY-MM-DD format (optional).

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
            curr_date: Current date in YYYY-MM-DD format (optional).

        Returns:
            Income statement data as formatted text.
        """
        return _get_income_statement(ticker, freq, curr_date)

    @mcp.tool()
    @_coerce_str_params
    def get_profit_forecast(
        ticker: str,
    ) -> str:
        """Retrieve consensus EPS forecasts with forward valuation metrics.

        Returns analyst coverage count, EPS by year (actual + estimates),
        forward PE, PEG, target price range, and PE digestion time
        from East Money datacenter (东方财富).

        Args:
            ticker: 6-digit A-stock code (e.g. 688017).

        Returns:
            Consensus forecast report with valuation metrics.
        """
        return _get_profit_forecast(ticker)

    # --- News ---

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

    # --- Shareholder ---

    @mcp.tool()
    @_coerce_str_params
    def get_insider_transactions(
        ticker: str,
    ) -> str:
        """Retrieve insider transaction / shareholder activity data.

        Uses 东方财富 F10 ShareholderResearch API for top 10 shareholders,
        top 10 free-float shareholders, holder count trends, and
        董监高持股变动明细 (executive shareholding changes).

        Args:
            ticker: 6-digit A-stock code (e.g. 600379).

        Returns:
            Insider transaction data as formatted text.
        """
        return _get_insider_transactions(ticker)

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

    # --- Capital Flow ---

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

    # --- Screening ---

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
    def get_company_announcements(
        ticker: str,
        category: str = "all",
        start_date: str = "",
        end_date: str = "",
        page_size: int = 30,
    ) -> str:
        """Retrieve company announcements from 巨潮资讯网 (cninfo.com.cn).

        Shows announcement title, date, type, and a direct PDF/HTML link.
        Covers annual/semi-annual/quarterly reports, major events, shareholders'
        meetings, and more.

        Args:
            ticker: 6-digit A-stock code (e.g. 600519).
            category: category alias — one of: all (default), annual (年报),
                half (半年报), quarterly_1 (一季报), quarterly_3 (三季报),
                major (重大事项), general_meeting (股东大会). Raw cninfo category
                codes are also accepted for advanced use.
            start_date: start date YYYY-MM-DD (empty = no lower bound).
            end_date: end date YYYY-MM-DD (empty = no upper bound).
            page_size: max announcements to return (server caps at 30).

        Returns:
            Announcement list with title, date, type, and document link.
        """
        return _get_company_announcements(ticker, category, start_date, end_date, page_size)

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

    @mcp.tool()
    @_coerce_str_params
    def get_ths_hot_list(
        span: str = "hour",
        limit: int = 50,
    ) -> str:
        """Get THS popularity hot list (同花顺热度榜) with AI reason tags.

        Returns stocks ranked by real-time popularity, each with a
        human-readable 上榜原因 and concept tags. Distinct from get_hot_stocks
        (which shows limit-up stocks only).

        Args:
            span: 'hour' for last-1-hour ranking, 'day' for today's ranking.
            limit: Maximum stocks to return (1-100, default 50).

        Returns:
            Hot list with rank, code, name, popularity score, change, tags, reason.
        """
        return _get_ths_hot_list(span, limit)
