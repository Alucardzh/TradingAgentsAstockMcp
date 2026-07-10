"""Market data tools — OHLCV K-lines, technical indicators, support/resistance, index, realtime."""

from __future__ import annotations

import urllib.request
from datetime import datetime
from typing import Annotated

import pandas as pd
from dateutil.relativedelta import relativedelta

from a_stock_mcp._core import (
    _em_get,
    _get_mootdx_client,
    _load_ohlcv_astock,
    _normalize_ticker,
    _sina_kline_fallback,
    _tencent_quote,
    logger,
)

# ===========================================================================
# 9 Vendor Methods (matching interface.py VENDOR_METHODS signatures)
# ===========================================================================


# ---- 1. get_stock_data ----


def get_stock_data(
    symbol: Annotated[str, "A-stock code (e.g. 688017, SH688017)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Get OHLCV stock price data via mootdx."""
    code = _normalize_ticker(symbol)

    data_source = "mootdx (TCP)"
    try:
        client = _get_mootdx_client()
        df = client.bars(symbol=code, category=4, offset=800)

        if df is None or df.empty:
            raise ValueError(f"No data from mootdx for {code}")

        # Drop duplicate datetime column + extra columns before reset_index
        df = df.drop(
            columns=["datetime", "year", "month", "day", "hour", "minute"],
            errors="ignore",
        )
        df = df.reset_index()  # index 'datetime' → column 'datetime'
        df = df.rename(
            columns={
                "datetime": "Date",
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
                "amount": "Amount",
            }
        )
        df["Date"] = pd.to_datetime(df["Date"])

    except Exception as e:
        logger.warning("mootdx K-line failed for %s: %s, trying sina HTTP fallback", code, e)
        # Fallback: Sina direct HTTP API
        try:
            df = _sina_kline_fallback(code, start_date, end_date)
            if df.empty:
                return "K线数据获取失败：mootdx和新浪备用源均不可用，请检查网络连接"
            data_source = "sina HTTP (fallback)"
        except Exception:
            return "K线数据获取失败：mootdx和新浪备用源均不可用，请检查网络连接"

    # Filter by date range
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    if df.empty:
        return f"No data found for A-stock '{code}' between {start_date} and {end_date}"

    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    csv_out = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(index=False)

    header = f"# Stock data for {code} (A-stock) from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data source: {data_source}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    header += "# Note: turnover rate (换手率) is not in OHLCV — use get_fundamentals(ticker) for it.\n\n"

    return header + csv_out



# ---- 2. get_indicators ----

# Supported technical indicators with descriptions
_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: Medium-term trend indicator.",
    "close_200_sma": "200 SMA: Long-term trend benchmark.",
    "close_10_ema": "10 EMA: Responsive short-term average.",
    "macd": "MACD: Momentum via EMA differences.",
    "macds": "MACD Signal: EMA smoothing of MACD line.",
    "macdh": "MACD Histogram: Gap between MACD and signal.",
    "rsi": "RSI: Momentum overbought/oversold indicator (70/30 thresholds).",
    "boll": "Bollinger Middle: 20 SMA basis for Bollinger Bands.",
    "boll_ub": "Bollinger Upper Band: 2 std devs above middle.",
    "boll_lb": "Bollinger Lower Band: 2 std devs below middle.",
    "atr": "ATR: Average True Range volatility measure.",
    "vwma": "VWMA: Volume-weighted moving average.",
    "mfi": "MFI: Money Flow Index (volume + price momentum).",
}


def get_indicators(
    symbol: Annotated[str, "A-stock code"],
    indicator: Annotated[str, "technical indicator (e.g. rsi, macd, close_50_sma, 'all')"],
    curr_date: Annotated[str, "Current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Get technical indicators using stockstats on mootdx OHLCV data."""
    from stockstats import wrap

    code = _normalize_ticker(symbol)

    if indicator == "all":
        indicators = list(_INDICATOR_DESCRIPTIONS.keys())
    elif indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(f"Indicator {indicator} not supported. Choose from: {list(_INDICATOR_DESCRIPTIONS.keys())}")
    else:
        indicators = [indicator]

    try:
        data = _load_ohlcv_astock(code, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        # Trigger stockstats calculation for all requested indicators
        for ind in indicators:
            df[ind]

        # Build date -> {indicator: value} lookup
        ind_dict = {}
        for _, row in df.iterrows():
            d = row["Date"]
            vals = {}
            for ind in indicators:
                v = row[ind]
                vals[ind] = "N/A" if pd.isna(v) else str(round(float(v), 4))
            ind_dict[d] = vals

        # Generate output for look_back window
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        before = curr_dt - relativedelta(days=look_back_days)

        lines = []
        dt = curr_dt
        while dt >= before:
            ds = dt.strftime("%Y-%m-%d")
            vals = ind_dict.get(ds)
            if vals is None:
                lines.append(f"{ds}: N/A: Not a trading day (weekend or holiday)")
            elif len(indicators) == 1:
                lines.append(f"{ds}: {vals[indicators[0]]}")
            else:
                parts = " | ".join(f"{ind}={vals[ind]}" for ind in indicators)
                lines.append(f"{ds}: {parts}")
            dt -= relativedelta(days=1)

        indicator_label = "all indicators" if indicator == "all" else indicator
        result = (
            f"## {indicator_label} for {code} "
            f"from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
            + "\n".join(lines)
            + "\n\n"
        )
        if indicator == "all":
            result += "Indicators: " + ", ".join(
                f"{ind} ({_INDICATOR_DESCRIPTIONS[ind]})" for ind in indicators
            )
        else:
            result += _INDICATOR_DESCRIPTIONS.get(indicator, "")
        return result

    except Exception as e:
        return f"Error calculating {indicator} for {code}: {str(e)}"


# ---- 3. calculate_support_resistance ----


def _cluster_price_levels(
    candidates: list[dict], n_target: int, merge_threshold: float = 0.02
) -> list[float]:
    """Cluster nearby price levels by strength (weighted average merge)."""
    if not candidates:
        return []

    candidates.sort(key=lambda x: x["strength"], reverse=True)

    clusters: list[dict] = []
    for cand in candidates:
        price = cand["price"]
        strength = cand["strength"]

        merged = False
        for cluster in clusters:
            if abs(price - cluster["price"]) / cluster["price"] < merge_threshold:
                total = cluster["strength"] + strength
                cluster["price"] = (cluster["price"] * cluster["strength"] + price * strength) / total
                cluster["strength"] = total
                cluster["count"] += 1
                merged = True
                break

        if not merged:
            clusters.append({"price": price, "strength": strength, "count": 1})

    clusters.sort(key=lambda x: x["strength"], reverse=True)
    return [c["price"] for c in clusters[:n_target]]


def calculate_support_resistance(
    symbol: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "Current date YYYY-MM-DD"],
    n_levels: Annotated[int, "number of support/resistance levels (1-10)"] = 5,
    lookback_period: Annotated[int, "lookback days (30-365)"] = 60,
) -> str:
    """Calculate support and resistance levels from historical price distribution.

    Uses a histogram-based algorithm: finds price zones where the stock spent
    the most time (highest frequency), then clusters nearby levels to avoid
    redundancy. Supports are in the bottom 40% of the range, resistances in
    the top 40%.

    Args:
        symbol: 6-digit A-stock code (e.g. 600519).
        curr_date: Current date YYYY-MM-DD (prevents look-ahead bias).
        n_levels: Number of levels per side (1-10, default 5).
        lookback_period: Analysis window in days (30-365, default 60).
    """
    code = _normalize_ticker(symbol)
    n_levels = max(1, min(int(n_levels), 10))
    lookback_period = max(30, min(int(lookback_period), 365))

    try:
        # Load OHLCV (mootdx → Sina fallback, cached, filtered by curr_date)
        df = _load_ohlcv_astock(code, curr_date)
        if df.empty:
            return f"No historical data for {code} to calculate support/resistance"

        prices = df["Close"].astype(float)
        lookback = min(lookback_period, len(prices))
        recent = prices.iloc[-lookback:]

        current_price = float(prices.iloc[-1])
        price_min = float(recent.min())
        price_max = float(recent.max())
        price_range = price_max - price_min

        if price_range == 0:
            return f"Cannot calculate S/R for {code}: price range is zero in the lookback period"

        # Histogram: find price zones with highest停留 frequency
        n_bins = 100
        counts, bin_edges = pd.cut(recent, bins=n_bins, labels=False, retbins=True)
        hist = counts.value_counts().sort_index()

        # Candidate levels: top 3x n_levels by frequency
        top_indices = hist.nlargest(n_levels * 3).index.tolist()

        support_candidates: list[dict] = []
        resistance_candidates: list[dict] = []

        for idx in top_indices:
            price_level = (bin_edges[idx] + bin_edges[idx + 1]) / 2
            percentile = (price_level - price_min) / price_range
            strength = int(hist.get(idx, 0)) / len(recent)

            if percentile < 0.4:
                support_candidates.append({"price": float(price_level), "strength": strength})
            elif percentile > 0.6:
                resistance_candidates.append({"price": float(price_level), "strength": strength})

        # Cluster + filter: supports below current price, resistances above
        support_levels = [
            s for s in _cluster_price_levels(support_candidates, n_levels) if s < current_price * 1.01
        ]
        resistance_levels = [
            r for r in _cluster_price_levels(resistance_candidates, n_levels) if r > current_price * 0.99
        ]

        # Volatility (annualized) and trend
        volatility = float(prices.pct_change().std() * (252**0.5))
        if lookback < len(prices):
            price_trend = "up" if prices.iloc[-1] > prices.iloc[-lookback] else "down"
        else:
            price_trend = "neutral"

        # Format output
        lines = [
            f"# Support & Resistance for {code} (A-stock)",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Lookback: {lookback} days | Current price: {current_price:.2f}",
            f"# Volatility (annualized): {volatility:.4f} | Trend: {price_trend}",
            "",
        ]

        lines.append("## Resistance Levels (压力位)")
        for i, r in enumerate(sorted(resistance_levels)):
            dist = (r - current_price) / current_price * 100
            lines.append(f"  R{i + 1}: {r:.2f} (+{dist:.1f}%)")

        lines.append("\n## Support Levels (支撑位)")
        for i, s in enumerate(sorted(support_levels, reverse=True)):
            dist = (current_price - s) / current_price * 100
            lines.append(f"  S{i + 1}: {s:.2f} (-{dist:.1f}%)")

        return "\n".join(lines)

    except Exception as e:
        return f"Error calculating support/resistance for {code}: {str(e)}"


# ---- 4. get_market_index ----


def _tencent_index_quote(code: str) -> dict | None:
    """Fetch a single market index quote from Tencent (qt.gtimg.cn).

    Index prefix rules differ from stocks: 399xxx → SZ, everything else → SH.
    Returns dict with name, current, last_close, change, change_pct, volume, amount.
    Returns None on failure.
    """
    # Index codes: 399xxx = SZ, 000xxx = SH (opposite of stock rules)
    prefix = "sz" if code.startswith("399") else "sh"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("gbk")
        if '="' not in raw:
            return None
        vals = raw.split('"')[1].split("~")
        if len(vals) < 34:
            return None
        # Tencent index field layout (verified 2026-07):
        # vals[1]=名称, vals[3]=最新价, vals[4]=昨收, vals[5]=今开,
        # vals[6]=成交量, vals[31]=涨跌额, vals[32]=涨跌幅(%),
        # vals[33]=最高, vals[34]=最低, vals[37]=成交额(万)
        name = vals[1] if vals[1] else code
        current = float(vals[3]) if vals[3] else 0
        last_close = float(vals[4]) if vals[4] else 0
        open_val = float(vals[5]) if vals[5] else 0
        volume = float(vals[6]) if vals[6] else 0
        change = float(vals[31]) if vals[31] else 0
        change_pct = float(vals[32]) if vals[32] else 0
        high = float(vals[33]) if vals[33] else 0
        low = float(vals[34]) if vals[34] else 0
        return {
            "name": name,
            "current": current,
            "last_close": last_close,
            "open": open_val,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "high": high,
            "low": low,
        }
    except Exception:
        return None


def get_market_index(
    index_code: Annotated[str, "index code (e.g. 000001 上证, 000300 沪深300, 399006 创业板指)"] = "000001",
) -> str:
    """Get real-time market index snapshot.

    Primary source: 东方财富 push2. Fallback: Tencent Finance (qt.gtimg.cn).

    Supports major A-share indices: 上证指数(000001), 沪深300(000300),
    上证50(000016), 创业板指(399006), 科创50(000688), 中证500(000905).

    Args:
        index_code: 6-digit index code (default 000001 for Shanghai Composite).
    """
    code = index_code.strip()

    # SZ indices start with 3 (secid prefix 0), all others use SH (prefix 1)
    secid = f"0.{code}" if code.startswith("3") else f"1.{code}"

    # --- Primary: Eastmoney push2his (push2 disconnects, push2his stable) ---
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/get"
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f169,f170,f171",
            "secid": secid,
        }
        r = _em_get(url, params=params, timeout=10)
        d = r.json().get("data", {})

        if d:
            name = d.get("f58", "N/A")
            current = d.get("f43", 0)
            change = d.get("f169", 0)
            change_pct = d.get("f170", 0)
            high = d.get("f44", 0)
            low = d.get("f45", 0)
            open_val = d.get("f46", 0)
            volume = d.get("f47", 0)
            amount = d.get("f48", 0)

            lines = [
            f"# Market Index: {code} ({name})",
            "# Source: 东方财富 push2his",
                f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                f"Current: {current}",
                f"Change: {change:+.2f} ({change_pct:+.2f}%)",
                f"Open: {open_val} | High: {high} | Low: {low}",
                f"Volume: {volume:,} | Amount: {amount / 1e8:.2f}亿",
            ]

            if change_pct > 0:
                lines.append("Signal: Market UP")
            elif change_pct < 0:
                lines.append("Signal: Market DOWN")

            return "\n".join(lines)
    except Exception as e:
        logger.warning("Eastmoney push2 index failed for %s: %s, trying Tencent fallback", code, e)

    # --- Fallback: Tencent Finance ---
    tq = _tencent_index_quote(code)
    if tq:
        lines = [
            f"# Market Index: {code} ({tq['name']})",
            "# Source: Tencent Finance (qt.gtimg.cn) — fallback",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Current: {tq['current']}",
            f"Change: {tq['change']:+.2f} ({tq['change_pct']:+.2f}%)",
            f"Open: {tq['open']} | High: {tq['high']} | Low: {tq['low']}",
            f"Volume: {tq['volume']:,.0f}",
        ]
        if tq["change_pct"] > 0:
            lines.append("Signal: Market UP")
        elif tq["change_pct"] < 0:
            lines.append("Signal: Market DOWN")
        return "\n".join(lines)

    return f"Error fetching market index {code}: both Eastmoney and Tencent failed"


# ---- 5. get_stock_realtime ----


def get_stock_realtime(
    symbol: Annotated[str, "A-stock code (e.g. 600519)"],
) -> str:
    """Get real-time stock price snapshot (current price, change, volume, amount).

    Lightweight single-stock quote from Tencent Finance. Faster than get_stock_data
    (which returns historical K-lines) when you only need the latest tick.

    Args:
        symbol: 6-digit A-stock code (e.g. 600519).
    """
    code = _normalize_ticker(symbol)

    try:
        tq = _tencent_quote([code])
        if code not in tq:
            return f"No realtime data found for A-stock '{code}'"

        q = tq[code]
        change = q["price"] - q["last_close"] if q["last_close"] else 0

        lines = [
            f"# Realtime Quote for {code} ({q['name']})",
            "# Source: Tencent Finance (qt.gtimg.cn)",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Price: {q['price']}",
            f"Change: {change:+.2f} ({q['change_pct']:+.2f}%)",
            f"Open: {q['open']} | High: {q['high']} | Low: {q['low']}",
            f"Last Close: {q['last_close']}",
            f"Volume: {q['volume']:,.0f}手 | Amount: {q['amount'] / 10000:.2f}亿",
            f"Turnover Rate: {q['turnover_pct']}%",
            f"Limit Up: {q['limit_up']} | Limit Down: {q['limit_down']}",
        ]

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching realtime data for {code}: {str(e)}"
