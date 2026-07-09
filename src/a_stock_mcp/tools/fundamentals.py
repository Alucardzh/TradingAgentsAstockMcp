"""Fundamental data tools — valuation, financial statements, EPS forecast."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated

import pandas as pd

from a_stock_mcp._core import (
    _UA,
    _em_eps_forecast,
    _em_get,
    _get_mootdx_client,
    _normalize_ticker,
    _requests,
    _tencent_quote,
    logger,
)

# ---- 3. get_fundamentals ----


def get_fundamentals(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "current date"] = None,
) -> str:
    """Get company fundamentals from Tencent + mootdx + Eastmoney."""
    code = _normalize_ticker(ticker)

    try:
        lines = []

        # --- Tencent: real-time valuation ---
        try:
            tq = _tencent_quote([code])
            if code in tq:
                q = tq[code]
                lines.extend(
                    [
                        f"Name: {q['name']}",
                        f"Price: {q['price']}",
                        f"PE (TTM): {q['pe_ttm']}",
                        f"PE (Static): {q['pe_static']}",
                        f"PB: {q['pb']}",
                        f"Market Cap (100M CNY): {q['mcap_yi']}",
                        f"Float Market Cap (100M CNY): {q['float_mcap_yi']}",
                        f"Turnover Rate: {q['turnover_pct']}%",
                        f"Change: {q['change_pct']}%",
                        f"Limit Up: {q['limit_up']}",
                        f"Limit Down: {q['limit_down']}",
                    ]
                )
        except Exception as e:
            logger.warning("Tencent quote failed for %s: %s", code, e)

        # --- mootdx: financial snapshot (quarterly) ---
        try:
            client = _get_mootdx_client()
            fin = client.finance(symbol=code)
            if fin is not None and not (isinstance(fin, pd.DataFrame) and fin.empty):
                row = fin.iloc[0] if isinstance(fin, pd.DataFrame) else fin
                field_map = {
                    "eps": "EPS (Quarterly)",
                    "bvps": "Book Value Per Share",
                    "roe": "ROE (%)",
                    "profit": "Net Profit",
                    "income": "Revenue",
                    "liutongguben": "Float Shares",
                    "zongguben": "Total Shares",
                }
                idx = row.index if hasattr(row, "index") else []
                for field, label in field_map.items():
                    if field in idx:
                        val = row[field]
                        if val is not None and str(val) != "nan":
                            lines.append(f"{label}: {val}")
        except Exception as e:
            logger.warning("mootdx finance failed for %s: %s", code, e)

        # --- Eastmoney push2: basic stock info (direct HTTP) ---
        try:
            market_code = 1 if code.startswith("6") else 0
            _info_url = "https://push2.eastmoney.com/api/qt/stock/get"
            _info_params = {
                "fltt": "2",
                "invt": "2",
                "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
                "secid": f"{market_code}.{code}",
            }
            r = _em_get(_info_url, params=_info_params, timeout=10)
            d = r.json().get("data", {})
            if d:
                if d.get("f127"):
                    lines.append(f"行业: {d['f127']}")
                if d.get("f84"):
                    lines.append(f"总股本: {d['f84']}")
                if d.get("f85"):
                    lines.append(f"流通股本: {d['f85']}")
                if d.get("f116"):
                    lines.append(f"总市值: {d['f116']}")
                if d.get("f117"):
                    lines.append(f"流通市值: {d['f117']}")
                if d.get("f189"):
                    lines.append(f"上市日期: {d['f189']}")
        except Exception as e:
            logger.warning("eastmoney push2 stock info failed for %s: %s", code, e)

        # --- Eastmoney datacenter: consensus EPS forecast ---
        # (Previously called _ths_eps_forecast, which was never defined — a dead
        #  NameError silently swallowed by the try/except, so consensus EPS never
        #  appeared in fundamentals output. Switched to the verified _em_eps_forecast
        #  dict API, same source as get_profit_forecast.)
        try:
            rec = _em_eps_forecast(code)
            if rec:
                org_num = rec.get("RATING_ORG_NUM", 0) or 0
                lines.append("\n--- Consensus EPS Forecast (东方财富) ---")
                lines.append(f"Analysts: {org_num}")
                if rec.get("DEC_AIMPRICEMAX") and rec.get("DEC_AIMPRICEMIN"):
                    lines.append(f"Target Price: {rec['DEC_AIMPRICEMIN']} ~ {rec['DEC_AIMPRICEMAX']}")

                eps_by_year: dict = {}
                for i in range(1, 5):
                    year = rec.get(f"YEAR{i}")
                    eps = rec.get(f"EPS{i}")
                    mark = rec.get(f"YEAR_MARK{i}", "?")
                    if year and eps is not None:
                        try:
                            eps = float(eps)
                        except (ValueError, TypeError):
                            continue
                        label = "Actual" if mark == "A" else "Estimate"
                        lines.append(f"FY{year}: EPS={eps:.2f} ({label})")
                        eps_by_year[year] = eps

                if org_num and org_num < 3:
                    lines.append("Warning: low coverage (<3 analysts)")

                # Forward PE / PEG / PE digestion (based on first estimate year)
                try:
                    tq = _tencent_quote([code])
                    if code in tq and eps_by_year:
                        price = tq[code]["price"]
                        years_sorted = sorted(eps_by_year.keys())
                        # first estimate year for forward PE
                        est_years = [
                            y
                            for y in years_sorted
                            if rec.get(f"YEAR_MARK{[i for i in range(1, 5) if rec.get(f'YEAR{i}') == y][0]}") == "E"
                        ]
                        fwd_year = est_years[0] if est_years else years_sorted[0]
                        eps_cur = eps_by_year.get(fwd_year, 0)
                        if eps_cur and eps_cur > 0:
                            fwd_pe = price / eps_cur
                            lines.append(
                                f"\nForward PE (FY{fwd_year}): {fwd_pe:.1f}x (price={price}, EPS={eps_cur})"
                            )
                            est_idx = years_sorted.index(fwd_year)
                            if est_idx + 1 < len(years_sorted):
                                eps_next = eps_by_year[years_sorted[est_idx + 1]]
                                if eps_next > 0:
                                    cagr = eps_next / eps_cur - 1
                                    if cagr > 0:
                                        peg = fwd_pe / (cagr * 100)
                                        lines.append(f"PEG: {peg:.2f} (EPS CAGR={cagr * 100:.0f}%)")
                                        if fwd_pe > 30:
                                            digest = math.log(fwd_pe / 30) / math.log(1 + cagr)
                                            lines.append(f"PE Digestion to 30x: {digest:.1f} years")
                                        else:
                                            lines.append("PE already below 30x target")
                                    else:
                                        lines.append(f"EPS declining ({cagr * 100:.0f}%), PEG not applicable")
                except Exception:
                    logger.exception("Forward PE calc failed for %s", code)
        except Exception:
            logger.exception("Consensus EPS forecast failed for %s", code)

        if not lines:
            return f"No fundamentals data found for A-stock '{code}'"

        header = f"# Company Fundamentals for {code} (A-stock)\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {code}: {str(e)}"


# ---- 4. get_balance_sheet ----


def _get_financial_report_sina(
    code: str,
    report_type: str,
    freq: str,
    curr_date: str = None,
) -> pd.DataFrame:
    """Shared helper: fetch financial report via Sina direct HTTP API.

    report_type: '资产负债表' | '利润表' | '现金流量表'

    Sina getFinanceReport2022 returns data under:
        result.data.report_list.{YYYYMMDD}.data[]
    where each entry is a list of {item_title, item_value, ...} line items.
    We pivot into a DataFrame with one row per report period.
    """
    _report_type_map = {
        "资产负债表": "fzb",
        "利润表": "lrb",
        "现金流量表": "llb",
    }
    source_type = _report_type_map.get(report_type, "lrb")

    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": source_type,
        "type": "0",
        "page": "1",
        "num": "20",
    }
    r = _requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=15)
    d = r.json()

    result_data = d.get("result", {}).get("data", {})
    report_list = result_data.get("report_list", {})
    if not report_list:
        return pd.DataFrame()

    # Collect date_type info from report_date for annual filtering
    report_dates = result_data.get("report_date", [])
    date_type_map = {rd["date_value"]: rd.get("date_type") for rd in report_dates}

    # Pivot: each report period becomes one row
    rows = []
    for date_str, entry in report_list.items():
        line_items = entry.get("data", [])
        if not line_items:
            continue
        row = {"报告日": date_str, "报告类型": entry.get("rType", "")}
        for item in line_items:
            row[item["item_title"]] = item["item_value"]
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Parse 报告日 as YYYYMMDD string → proper date
    df["报告日"] = pd.to_datetime(df["报告日"], format="%Y%m%d", errors="coerce")

    # Filter by curr_date
    if curr_date and "报告日" in df.columns:
        cutoff = pd.to_datetime(curr_date)
        df = df[df["报告日"] <= cutoff]

    # Filter by frequency: annual = date_type 4 (年报)
    if freq.lower() == "annual" and "报告日" in df.columns:
        # Use date_type_map: type 4 = 年报
        df["_date_key"] = df["报告日"].dt.strftime("%Y%m%d")
        df = df[df["_date_key"].map(lambda x: date_type_map.get(x) == 4)]
        df = df.drop(columns=["_date_key"])

    # Sort newest first, limit to 8 periods
    df = df.sort_values("报告日", ascending=False).head(8).reset_index(drop=True)

    return df


def get_balance_sheet(
    ticker: Annotated[str, "A-stock code"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet via Sina direct HTTP API."""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(code, "资产负债表", freq, curr_date)

        if df.empty:
            return f"No balance sheet data found for A-stock '{code}'"

        csv_string = df.to_csv(index=False)

        header = f"# Balance Sheet for {code} (A-stock, {freq})\n"
        header += "# Data source: sina direct HTTP\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving balance sheet for {code}: {str(e)}"


# ---- 5. get_cashflow ----


def get_cashflow(
    ticker: Annotated[str, "A-stock code"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow statement via Sina direct HTTP API."""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(code, "现金流量表", freq, curr_date)

        if df.empty:
            return f"No cash flow data found for A-stock '{code}'"

        csv_string = df.to_csv(index=False)

        header = f"# Cash Flow for {code} (A-stock, {freq})\n"
        header += "# Data source: sina direct HTTP\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving cash flow for {code}: {str(e)}"


# ---- 6. get_income_statement ----


def get_income_statement(
    ticker: Annotated[str, "A-stock code"],
    freq: Annotated[str, "frequency: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement via Sina direct HTTP API."""
    code = _normalize_ticker(ticker)

    try:
        df = _get_financial_report_sina(code, "利润表", freq, curr_date)

        if df.empty:
            return f"No income statement data found for A-stock '{code}'"

        csv_string = df.to_csv(index=False)

        header = f"# Income Statement for {code} (A-stock, {freq})\n"
        header += "# Data source: sina direct HTTP\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving income statement for {code}: {str(e)}"


# ---- 10. get_profit_forecast ----


def get_profit_forecast(
    ticker: Annotated[str, "A-stock code"],
    curr_date: Annotated[str, "current date (unused, for interface compat)"] = None,
) -> str:
    """Get consensus EPS forecasts with forward valuation (East Money datacenter)."""
    code = _normalize_ticker(ticker)

    try:
        rec = _em_eps_forecast(code)

        if rec is None:
            return f"No analyst coverage found for A-stock '{code}'"

        lines = [
            f"# Consensus EPS Forecast for {code} (A-stock)",
            "# Source: 东方财富 analyst consensus (datacenter-web)",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        org_num = rec.get("RATING_ORG_NUM", 0) or 0
        buy_num = rec.get("RATING_BUY_NUM", 0) or 0
        add_num = rec.get("RATING_ADD_NUM", 0) or 0
        industry = rec.get("INDUSTRY_BOARD", "N/A")
        aim_max = rec.get("DEC_AIMPRICEMAX")
        aim_min = rec.get("DEC_AIMPRICEMIN")
        lines.append(f"Analysts: {org_num} (Buy={buy_num}, Add={add_num})")
        lines.append(f"Industry: {industry}")
        if aim_max and aim_min:
            lines.append(f"Target Price: {aim_min} ~ {aim_max}")

        # EPS by year (up to 4 years)
        eps_by_year: dict[int, float] = {}
        for i in range(1, 5):
            year = rec.get(f"YEAR{i}")
            eps = rec.get(f"EPS{i}")
            mark = rec.get(f"YEAR_MARK{i}", "?")
            if year and eps is not None:
                eps = float(eps)
                label = "Actual" if mark == "A" else "Estimate"
                lines.append(f"FY{year}: EPS={eps:.2f} ({label})")
                eps_by_year[year] = eps

        if org_num > 0 and org_num < 3:
            lines.append("Warning: low coverage (<3 analysts)")

        # Forward valuation
        try:
            tq = _tencent_quote([code])
            if code in tq:
                price = tq[code]["price"]
                pe_ttm = tq[code]["pe_ttm"]
                lines.append(f"\nCurrent: price={price}, PE(TTM)={pe_ttm}")

                years_sorted = sorted(eps_by_year.keys())
                # Find the first "E" (estimate) year for forward PE
                def _year_mark(rec, year):
                    """Look up YEAR_MARKn for a given year value."""
                    for i in range(1, 5):
                        if rec.get(f"YEAR{i}") == year:
                            return rec.get(f"YEAR_MARK{i}", "?")
                    return "?"

                est_years = [y for y in years_sorted if _year_mark(rec, y) == "E"]
                if est_years:
                    fwd_year = est_years[0]
                    fwd_eps = eps_by_year[fwd_year]
                    if fwd_eps > 0:
                        fwd_pe = price / fwd_eps
                        lines.append(f"Forward PE (FY{fwd_year}): {fwd_pe:.1f}x")
                        # Find next estimate year for CAGR
                        est_idx = years_sorted.index(fwd_year)
                        if est_idx + 1 < len(years_sorted):
                            next_year = years_sorted[est_idx + 1]
                            next_eps = eps_by_year[next_year]
                            if fwd_eps > 0:
                                cagr = next_eps / fwd_eps - 1
                                if cagr > 0:
                                    peg = fwd_pe / (cagr * 100)
                                    lines.append(f"PEG: {peg:.2f} (CAGR={cagr * 100:.0f}%)")
                                    if fwd_pe > 30:
                                        digest = math.log(fwd_pe / 30) / math.log(1 + cagr)
                                        lines.append(f"PE Digestion to 30x: {digest:.1f} years")
                                else:
                                    lines.append(f"EPS declining ({cagr * 100:.0f}%), PEG not applicable")
        except Exception as e:
            logger.warning("Forward PE calc failed for %s: %s", code, e)

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving profit forecast for {code}: {str(e)}"
