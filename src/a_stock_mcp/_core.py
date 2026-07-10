"""A-stock shared infrastructure — ticker resolution, mootdx client,
and multi-vendor HTTP helpers (Tencent / Eastmoney / Sina).

All tool modules import from here. This module has no dependency on
any tool module.

Data sources:
- mootdx (TCP 7709): OHLCV K-lines, financial snapshots, F10 text
- Tencent Finance (HTTP GBK): PE/PB/market cap/turnover
- 东方财富 push2 / datacenter-web (direct HTTP): stock info, dragon-tiger, lockup,
  executive hold-changes, consensus EPS forecast
- 新浪财经 (direct HTTP): K-line fallback, financial statements
- 同花顺 (direct HTTP): hot stocks, northbound capital flow
- 财联社 (direct HTTP): global news wire
- 巨潮资讯网 cninfo (direct HTTP): company announcements
"""

from __future__ import annotations

import json as _json
import logging
import os
import random
import re as _re
import time
import urllib.request
from datetime import datetime

import pandas as pd
import requests as _requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 可选：东财代理 fallback（当 AKPROXY_TOKEN 非空且 curl_cffi 已安装时启用）
# 直连东财失败（RemoteDisconnected / IP 封禁）时，自动 fallback 到代理：
#   curl_cffi 浏览器指纹 + 轮换代理 IP + Cookie 绕过风控。
# 安装：pip install curl_cffi （或 uv sync --extra proxy）
# ---------------------------------------------------------------------------
_AKPROXY_TOKEN = os.environ.get("AKPROXY_TOKEN", "")
_AKPROXY_IP = os.environ.get("AKPROXY_IP", "101.201.173.125")
_AKPROXY_AVAILABLE = False

if _AKPROXY_TOKEN:
    try:
        from curl_cffi import requests as _cffi_requests
        from curl_cffi.requests import BrowserType as _BrowserType

        _AKPROXY_BROWSERS = [
            b
            for b in _BrowserType.__dict__.values()
            if isinstance(b, str) and (b.startswith("chrome") or b.startswith("edge"))
        ]
        _AKPROXY_AVAILABLE = True
        logger.info("AKPROXY_TOKEN detected — Eastmoney proxy fallback enabled")
    except ImportError:
        logger.warning(
            "AKPROXY_TOKEN set but curl_cffi not installed. "
            "Install with: uv sync --extra proxy"
        )

# Proxy auth cache (refreshed every 28s, same as akshare_proxy_patch)
_proxy_auth_cache: dict | None = None
_proxy_auth_expire: float = 0.0


def _get_proxy_auth() -> dict | None:
    """Fetch proxy config (cookie + proxy URL) from akshare-proxy auth server."""
    global _proxy_auth_cache, _proxy_auth_expire
    now = time.time()
    if _proxy_auth_cache and now < _proxy_auth_expire:
        return _proxy_auth_cache
    try:
        auth_url = f"http://{_AKPROXY_IP}:47001/api/akshare-auth"
        r = _requests.get(auth_url, params={"token": _AKPROXY_TOKEN, "version": "0.5.0"}, timeout=(1.5, 3))
        data = r.json()
        if data.get("ua"):
            _proxy_auth_cache = data
            _proxy_auth_expire = now + 28
            return data
        logger.warning("AKProxy auth failed: %s", data.get("error_msg", "unknown"))
    except Exception:
        pass
    return _proxy_auth_cache  # may be stale or None


def _em_proxy_get(url, params=None, headers=None, timeout=15, max_retries=5):
    """Fallback: fetch an Eastmoney URL via curl_cffi proxy when direct connection is banned.

    Uses browser fingerprint spoofing + rotating proxy IP + cookie from the
    akshare-proxy auth server. Mirrors the core logic of akshare_proxy_patch
    but as an explicit fallback (not a global monkey-patch).
    """
    for attempt in range(max_retries):
        auth = _get_proxy_auth()
        if not auth:
            time.sleep(0.1)
            continue

        merged_headers = dict(headers or {})
        merged_headers["Cookie"] = auth.get("cookie", "")
        proxy_url = auth.get("proxy", "")
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

        try:
            with _cffi_requests.Session() as s:
                resp = s.get(
                    url,
                    params=params,
                    headers=merged_headers,
                    proxies=proxies,
                    timeout=timeout,
                    impersonate=random.choice(_AKPROXY_BROWSERS),
                )
                if resp.status_code == 200:
                    return resp
                logger.warning("AKProxy attempt %d: HTTP %d", attempt + 1, resp.status_code)
        except Exception as e:
            logger.warning("AKProxy attempt %d failed: %s", attempt + 1, e)
        # Invalidate auth cache on failure
        _proxy_auth_expire = 0.0
        time.sleep(0.1)

    raise _requests.exceptions.ConnectionError(f"AKProxy fallback exhausted after {max_retries} retries for {url}")

# Cache directory (overridable via ASTOCK_CACHE_DIR env var)
_CACHE_DIR = os.environ.get(
    "ASTOCK_CACHE_DIR",
    os.path.join(os.path.expanduser("~"), ".astock-mcp", "cache"),
)

def safe_ticker_component(value: str) -> str:
    """Validate and sanitize a ticker string for safe filesystem usage.

    If the value contains Chinese characters, auto-resolves to a 6-digit
    A-stock code via the name-code map (lazy-loaded from mootdx).
    """
    if not value or not isinstance(value, str):
        raise ValueError("ticker must be a non-empty string")
    value = value.strip()
    has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in value)
    if has_chinese:
        return resolve_ticker(value)
    if len(value) > 32:
        raise ValueError(f"ticker too long ({len(value)} chars): {value!r}")
    if value.strip(".") == "":
        raise ValueError(f"ticker cannot be all dots: {value!r}")
    if not _re.match(r"^[A-Za-z0-9._\-\^]+$", value):
        raise ValueError(
            f"ticker contains unsafe characters: {value!r} (only alphanumeric, dot, hyphen, underscore, caret allowed)"
        )
    return value


# ---------------------------------------------------------------------------
# Helpers: ticker format & market detection
# ---------------------------------------------------------------------------


def _get_prefix(code: str) -> str:
    """6-digit A-stock code -> market prefix for Tencent API."""
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"


def _normalize_ticker(symbol: str) -> str:
    """Strip exchange prefix/suffix, return pure 6-digit code.

    Handles: '688017', 'SH688017', '688017.SH', 'sh688017'
    """
    s = symbol.strip().upper()
    # Remove .SH / .SZ / .BJ suffix
    for suffix in (".SH", ".SZ", ".BJ"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    # Remove SH / SZ / BJ prefix
    for prefix in ("SH", "SZ", "BJ"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    return safe_ticker_component(s)


# ---------------------------------------------------------------------------
# Stock name <-> code mapping (cached)
# ---------------------------------------------------------------------------

_name_to_code: dict[str, str] | None = None
_code_to_name: dict[str, str] | None = None


def _build_name_code_map() -> tuple[dict[str, str], dict[str, str]]:
    """Build name->code and code->name maps via mootdx (both SH & SZ markets).

    Returns empty dicts if mootdx is unavailable (caller should handle).
    """
    global _name_to_code, _code_to_name
    if _name_to_code is not None:
        return _name_to_code, _code_to_name

    n2c: dict[str, str] = {}
    c2n: dict[str, str] = {}

    client = _get_mootdx_client()
    if client is None:
        logger.warning("mootdx unavailable, name-code map is empty; Chinese name lookup disabled")
        _name_to_code = n2c
        _code_to_name = c2n
        return _name_to_code, _code_to_name

    for market in (0, 1):  # 0=SZ, 1=SH
        stocks = client.stocks(market=market)
        if stocks is None or stocks.empty:
            continue
        for _, row in stocks.iterrows():
            code = str(row["code"]).strip()
            name = str(row["name"]).strip()
            if not _re.match(r"^[036]\d{5}$", code):
                continue
            clean_name = name.replace(" ", "").replace("　", "")
            n2c[clean_name] = code
            c2n[code] = clean_name

    _name_to_code = n2c
    _code_to_name = c2n
    logger.info("Built stock name-code map: %d entries", len(n2c))
    return _name_to_code, _code_to_name


def resolve_ticker(user_input: str) -> str:
    """Resolve user input (code or Chinese name) to a 6-digit A-stock code.

    Accepts: '600379', 'SH600379', '600379.SH', '宝光股份'
    Returns: '600379'
    Raises: ValueError if not resolvable.
    """
    s = user_input.strip()
    if not s:
        raise ValueError("输入不能为空")

    has_chinese = any("一" <= ch <= "鿿" for ch in s)

    if not has_chinese:
        return _normalize_ticker(s)

    clean = s.replace(" ", "").replace("　", "")
    n2c, _ = _build_name_code_map()

    if not n2c:
        raise ValueError(f"无法解析中文股票名 '{s}'：mootdx 行情服务器连接失败，请直接使用 6 位数字代码（如 600519）")

    if clean in n2c:
        return n2c[clean]

    matches = {name: code for name, code in n2c.items() if clean in name}
    if len(matches) == 1:
        return next(iter(matches.values()))
    if len(matches) > 1:
        examples = ", ".join(f"{n}({c})" for n, c in list(matches.items())[:5])
        raise ValueError(f"'{s}' 匹配到多只股票: {examples}，请输入完整名称或代码")

    raise ValueError(f"找不到股票 '{s}'，请检查名称是否正确")

# ---------------------------------------------------------------------------
# mootdx client (singleton)
# ---------------------------------------------------------------------------

_mootdx_client = None
_mootdx_client_error: str | None = None


def _get_mootdx_client():
    """Lazy-init mootdx Quotes client (TCP connection, reusable).

    Tries multiple server endpoints. Returns None and sets
    _mootdx_client_error if all connections fail.
    """
    global _mootdx_client, _mootdx_client_error
    if _mootdx_client is not None:
        return _mootdx_client
    if _mootdx_client_error is not None:
        return None

    from mootdx import config as mootdx_config
    from mootdx.quotes import Quotes

    # mootdx Quotes.factory ignores ip=/port= kwargs — the __init__ reads
    # BESTIP from config. We must set it before each attempt.
    # ponytail: hard-coded fallback list, fetch live bestip if this stops working
    for server in [
        ("112.74.214.43", 7727),   #腾讯双线
        ("110.41.147.114", 7709),  #阿里双线1
        ("8.129.13.54", 7709),     #阿里双线2
        ("120.24.149.49", 7709),   #阿里双线3
    ]:
        try:
            mootdx_config.set("BESTIP", {"HQ": server})
            client = Quotes.factory(market="std")
            test = client.stocks(market=1)
            if test is not None:
                _mootdx_client = client
                logger.info("mootdx connected to %s:%s", server[0], server[1])
                return _mootdx_client
        except Exception as e:
            logger.warning("mootdx connect failed (%s:%s): %s", server[0], server[1], e)
            continue

    _mootdx_client_error = (
        "mootdx 连接失败：无法连接到通达信行情服务器。"
        "K线/技术指标/股东数据不可用，其余工具（新闻/基本面/资金流向等）正常。"
        "如需修复请检查网络是否允许 TCP 7709 端口出站。"
    )
    logger.error(_mootdx_client_error)
    return None

# ---------------------------------------------------------------------------
# Tencent Finance API
# ---------------------------------------------------------------------------


def _tencent_quote(codes: list[str]) -> dict[str, dict]:
    """Batch real-time quotes from Tencent Finance (qt.gtimg.cn).

    Returns dict[code] -> {name, price, pe_ttm, pb, mcap_yi, ...}
    """
    prefixed = [f"{_get_prefix(c)}{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")

    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]  # strip sh/sz/bj prefix
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "volume": float(vals[36]) if vals[36] else 0,
            "amount": float(vals[37]) if vals[37] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "float_mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return result



# ---------------------------------------------------------------------------
# Eastmoney Datacenter unified helper (龙虎榜/解禁 etc.)
# ---------------------------------------------------------------------------

_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# 东财防封：全局节流 + 会话复用 (Eastmoney anti-ban: throttle + Keep-Alive)
# ---------------------------------------------------------------------------
# 东财系 HTTP 接口（push2 / push2his / datacenter-web / search-api / np-weblist）
# 有风控：每秒 >5 次 / 单 IP 并发 ≥10 / 1 分钟 ≥200 次 / 5 分钟 ≥300 次 → 临时封 IP。
# 多 Agent 投研跑批量分析时会高频请求东财，是被封的头号元凶。所有 eastmoney.com
# 请求一律走 _em_get()：串行限流（最小间隔 + 随机抖动）+ 复用 Keep-Alive 会话 + 默认 UA。
# 注意：仅东财接口走此入口；mootdx(TCP) / 腾讯 / 新浪 / 同花顺 / 财联社 / 百度 等
# 不限流（实测不封 IP 或风控极弱）。批量任务可调大 EM_MIN_INTERVAL 进一步降速。
_EM_SESSION = _requests.Session()
_EM_SESSION.trust_env = False  # ignore shell HTTPS_PROXY — EM endpoints must connect directly
_EM_SESSION.headers.update({"User-Agent": _UA})
# 两次东财请求最小间隔(秒)；批量多 Agent 场景可设环境变量 EM_MIN_INTERVAL=1.5~2 降速。
_EM_MIN_INTERVAL = float(os.environ.get("EM_MIN_INTERVAL", "1.0"))
_em_last_call = [0.0]  # 模块级上次东财请求时间戳


def _em_get(url, params=None, headers=None, timeout=15, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。

    所有 eastmoney.com 接口都应通过它请求，避免多 Agent 高频拉数据被封 IP。
    串行限流：与上次东财请求间隔 < EM_MIN_INTERVAL 时 sleep 补足 + 0.1~0.5s 随机抖动。
    传入的 headers 会覆盖 session 默认 UA（用于保留各端点自己的 Referer/Origin）。
    直连失败时：先重试 1 次，仍失败则尝试 AKProxy 代理 fallback（需配置 AKPROXY_TOKEN）。
    """
    wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))

    # --- 直连 ---
    try:
        return _EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    except (_requests.exceptions.ConnectionError, _requests.exceptions.ChunkedEncodingError):
        logger.warning("东财直连失败，1s 后重试: %s", url)
        time.sleep(1)
        try:
            return _EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
        except (_requests.exceptions.ConnectionError, _requests.exceptions.ChunkedEncodingError):
            # --- 直连彻底失败，尝试代理 fallback ---
            if _AKPROXY_AVAILABLE:
                logger.warning("东财直连仍失败，切换到 AKProxy 代理: %s", url)
                try:
                    resp = _em_proxy_get(url, params=params, headers=headers, timeout=timeout)
                    _em_last_call[0] = time.time()
                    return resp
                except Exception:
                    pass  # fall through to re-raise original error
            raise
    finally:
        _em_last_call[0] = time.time()


def _eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> list[dict]:
    """东财数据中心统一查询 — 龙虎榜/解禁 共用."""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    r = _em_get(_DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ---------------------------------------------------------------------------
# Consensus EPS forecast helper (East Money datacenter, replaces THS HTML scraping)
# ---------------------------------------------------------------------------


def _em_eps_forecast(code: str) -> dict | None:
    """Fetch consensus EPS forecast from 东方财富 datacenter API.

    Returns dict with keys: RATING_ORG_NUM, YEAR1..4, EPS1..4, YEAR_MARK1..4,
    DEC_AIMPRICEMAX, DEC_AIMPRICEMIN, INDUSTRY_BOARD, etc.  Or None on failure.
    """
    data = _eastmoney_datacenter(
        report_name="RPT_WEB_RESPREDICT",
        columns="ALL",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=5,
    )
    if data:
        return data[0]
    return None



# ---------------------------------------------------------------------------
# Sina K-line fallback helper (direct HTTP, no akshare)
# ---------------------------------------------------------------------------


def _sina_kline_fallback(code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Fetch daily K-line from Sina HTTP API as mootdx fallback.

    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume.
    """
    prefix = "sh" if code.startswith("6") else "sz"
    url = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": f"{prefix}{code}",
        "scale": "240",  # daily
        "ma": "no",
        "datalen": "800",
    }
    r = _requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = _json.loads(r.text)

    if not data:
        return pd.DataFrame()

    rows = []
    for item in data:
        rows.append(
            {
                "Date": item["day"],
                "Open": float(item["open"]),
                "High": float(item["high"]),
                "Low": float(item["low"]),
                "Close": float(item["close"]),
                "Volume": int(item["volume"]),
            }
        )

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])

    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]

    return df



# ---------------------------------------------------------------------------
# OHLCV loading with cache (mootdx -> CSV)
# ---------------------------------------------------------------------------


def _load_ohlcv_astock(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV via mootdx, cache to CSV, filter by curr_date.

    Mirrors stockstats_utils.load_ohlcv but uses mootdx instead of yfinance.
    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume
    """
    code = _normalize_ticker(symbol)
    cache_dir = _CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    cache_file = os.path.join(cache_dir, f"{code}-astock-daily.csv")

    if os.path.exists(cache_file):
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        if mtime.date() == datetime.now().date():
            data = pd.read_csv(cache_file, on_bad_lines="skip", encoding="utf-8")
            data["Date"] = pd.to_datetime(data["Date"])
            cutoff = pd.to_datetime(curr_date)
            return data[data["Date"] <= cutoff]

    # Fetch from mootdx — 800 daily bars (~3 years of trading days)
    try:
        client = _get_mootdx_client()
        df = client.bars(symbol=code, category=4, offset=800)

        if df is None or df.empty:
            raise ValueError(f"No OHLCV data from mootdx for {code}")

        # mootdx returns index named 'datetime' AND a column named 'datetime'
        # (plus year/month/day/hour/minute/volume). Drop duplicates before reset.
        df = df.drop(columns=["datetime", "year", "month", "day", "hour", "minute"], errors="ignore")
        df = df.reset_index()  # moves index 'datetime' → column 'datetime'
        rename_map = {
            "datetime": "Date",
            "open": "Open",
            "close": "Close",
            "high": "High",
            "low": "Low",
            "volume": "Volume",
        }
        df = df.rename(columns=rename_map)
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df["Date"] = pd.to_datetime(df["Date"])
    except Exception as e:
        logger.warning("mootdx OHLCV failed for %s: %s, trying sina HTTP fallback", code, e)
        # Fallback: Sina direct HTTP API
        try:
            df = _sina_kline_fallback(code)
            if df.empty:
                raise ValueError(f"No OHLCV data from sina for {code}") from e
        except Exception as err:
            raise ValueError(f"No OHLCV data from mootdx/sina for {code}") from err

    # Cache to disk
    df.to_csv(cache_file, index=False, encoding="utf-8")

    # Filter by curr_date to prevent look-ahead bias
    cutoff = pd.to_datetime(curr_date)
    return df[df["Date"] <= cutoff]
