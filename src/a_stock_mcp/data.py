"""Backward-compat shim — functions moved to a_stock_mcp._core and a_stock_mcp.tools.

Historical import ``from a_stock_mcp.data import get_stock_data`` still works;
new code should import from ``a_stock_mcp.tools`` instead.
"""

from a_stock_mcp._core import (  # noqa: F401
    _CACHE_DIR,
    _DATACENTER_URL,
    _EM_MIN_INTERVAL,
    _EM_SESSION,
    _UA,
    _build_name_code_map,
    _code_to_name,
    _eastmoney_datacenter,
    _em_eps_forecast,
    _em_get,
    _em_last_call,
    _get_mootdx_client,
    _get_prefix,
    _load_ohlcv_astock,
    _mootdx_client,
    _mootdx_client_error,
    _name_to_code,
    _normalize_ticker,
    _sina_kline_fallback,
    _tencent_quote,
    logger,
    resolve_ticker,
    safe_ticker_component,
)
from a_stock_mcp.tools import (  # noqa: F401
    get_balance_sheet,
    get_cashflow,
    get_company_announcements,
    get_concept_blocks,
    get_dragon_tiger_board,
    get_fund_flow,
    get_fundamentals,
    get_global_news,
    get_hot_stocks,
    get_income_statement,
    get_indicators,
    get_industry_comparison,
    get_insider_transactions,
    get_lockup_expiry,
    get_news,
    get_northbound_flow,
    get_profit_forecast,
    get_stock_data,
)
