"""Shareholder data tools — insider transactions and lockup expiry."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import pandas as pd

from a_stock_mcp._core import (
    _eastmoney_datacenter,
    _em_get,
    _normalize_ticker,
    logger,
    safe_ticker_component,
)

# ---- 9. get_insider_transactions ----


def get_insider_transactions(
    ticker: Annotated[str, "A-stock code"],
) -> str:
    """Get shareholder/insider activity via 东方财富 F10 + datacenter API.

    Note: A-stock insider transaction data differs from US markets.
    Shows top 10 shareholders, top 10 free-float shareholders, holder count trends,
    and 董监高持股变动明细 (executive/supervisor/manager individual shareholding changes).
    """
    code = _normalize_ticker(ticker)
    prefix = "SH" if code.startswith("6") else "SZ"

    lines = [
        f"# Shareholder Research for {code} (A-stock)",
        "# Note: A-stock equivalent of insider transactions",
        "# Data source: 东方财富 F10 ShareholderResearch",
        f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    try:
        url = "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax"
        r = _em_get(url, params={"code": f"{prefix}{code}"}, timeout=15)
        d = r.json()

        # 1. Top 10 shareholders (十大股东)
        sdgd = d.get("sdgd", [])
        if sdgd:
            by_date: dict[str, list] = {}
            for item in sdgd:
                end_date = (item.get("END_DATE") or "")[:10]
                if end_date not in by_date:
                    by_date[end_date] = []
                by_date[end_date].append(item)

            for date in sorted(by_date.keys(), reverse=True)[:2]:
                items = by_date[date]
                lines.append(f"\n## 十大股东 ({date})")
                lines.append("排名 | 股东名称 | 持股数(万股) | 占总股本(%) | 变动")
                for item in items:
                    rank = item.get("HOLDER_RANK", "-")
                    name = item.get("HOLDER_NAME", "N/A")
                    hold = item.get("HOLD_NUM", 0)
                    ratio = item.get("HOLD_NUM_RATIO", 0)
                    change = item.get("HOLD_NUM_CHANGE", "N/A")
                    hold_wan = f"{hold / 10000:.0f}" if hold else "0"
                    lines.append(f"  {rank}. {name} | {hold_wan} | {ratio} | {change}")

        # 2. Top 10 free-float shareholders (十大流通股东)
        sdltgd = d.get("sdltgd", [])
        if sdltgd:
            by_date2: dict[str, list] = {}
            for item in sdltgd:
                end_date = (item.get("END_DATE") or "")[:10]
                if end_date not in by_date2:
                    by_date2[end_date] = []
                by_date2[end_date].append(item)

            for date in sorted(by_date2.keys(), reverse=True)[:2]:
                items = by_date2[date]
                lines.append(f"\n## 十大流通股东 ({date})")
                lines.append("排名 | 股东名称 | 持股数(万股) | 占流通股(%) | 变动")
                for item in items:
                    rank = item.get("HOLDER_RANK", "-")
                    name = item.get("HOLDER_NAME", "N/A")
                    hold = item.get("HOLD_NUM", 0)
                    ratio = item.get("FREE_HOLDNUM_RATIO", 0)
                    change = item.get("HOLD_NUM_CHANGE", "N/A")
                    hold_wan = f"{hold / 10000:.0f}" if hold else "0"
                    ratio_str = f"{ratio:.2f}" if isinstance(ratio, (int, float)) else str(ratio)
                    lines.append(f"  {rank}. {name} | {hold_wan} | {ratio_str} | {change}")

        # 3. Shareholder count trend (股东户数变化)
        gdrs = d.get("gdrs", [])
        if gdrs:
            lines.append("\n## 股东户数变化")
            lines.append("日期 | 股东户数 | 较上期变化(%) | 户均持股(股)")
            for item in gdrs:
                end_date = (item.get("END_DATE") or "")[:10]
                count = item.get("HOLDER_TOTAL_NUM")
                ratio = item.get("TOTAL_NUM_RATIO")
                avg_shares = item.get("AVG_FREE_SHARES")
                count_str = f"{count:,}" if count else "N/A"
                ratio_str = f"{ratio:.2f}%" if isinstance(ratio, (int, float)) else "N/A"
                avg_str = f"{avg_shares:.0f}" if isinstance(avg_shares, (int, float)) else "N/A"
                lines.append(f"  {end_date} | {count_str} | {ratio_str} | {avg_str}")

        # 4. 董监高持股变动明细 (executive/supervisor/manager shareholding changes)
        # Eastmoney datacenter reportName=RPT_EXECUTIVE_HOLD_DETAILS — individual
        # directors/supervisors/managers' buy/sell transactions, distinct from the
        # top-10 shareholder rankings above. Field names verified against live API.
        hold_changes: list[dict] = []
        try:
            hold_changes = _eastmoney_datacenter(
                report_name="RPT_EXECUTIVE_HOLD_DETAILS",
                filter_str=f'(SECURITY_CODE="{code}")',
                sort_columns="CHANGE_DATE",
                sort_types="-1",
                page_size=50,
            )
        except Exception:
            logger.exception("Executive hold-change query failed for %s", code)

        if hold_changes:
            lines.append("\n## 董监高持股变动明细")
            lines.append("# 数据来源: 东方财富 datacenter RPT_EXECUTIVE_HOLD_DETAILS")
            lines.append("日期 | 变动人 | 变动股数 | 成交均价 | 变动后持股 | 变动原因 | 职务")
            for item in hold_changes[:20]:  # cap at 20 most recent
                d_val = (item.get("CHANGE_DATE") or "")[:10]
                changer = item.get("PERSON_NAME", "N/A")
                num = item.get("CHANGE_SHARES", 0)
                price = item.get("AVERAGE_PRICE", 0)
                after = item.get("CHANGE_AFTER_HOLDNUM", 0)
                reason = item.get("CHANGE_REASON", "N/A")
                job = item.get("POSITION_NAME", "N/A")
                num_str = f"{num:+,}" if isinstance(num, (int, float)) else str(num)
                price_str = f"{price:.2f}" if isinstance(price, (int, float)) else str(price)
                after_str = f"{after:,}" if isinstance(after, (int, float)) else str(after)
                lines.append(
                    f"  {d_val} | {changer} | {num_str} | {price_str} | {after_str} | {reason} | {job}"
                )
            if len(hold_changes) > 20:
                lines.append(f"  ... 共 {len(hold_changes)} 条，仅显示最近 20 条")

        if not sdgd and not sdltgd and not gdrs and not hold_changes:
            return f"No insider/shareholder data found for A-stock '{code}'"

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving insider/shareholder data for {code}: {str(e)}"


# ---------------------------------------------------------------------------
# 16. Lockup Expiry Calendar (限售解禁日历)
# ---------------------------------------------------------------------------


def get_lockup_expiry(
    ticker: str,
    trade_date: str,
    forward_days: int = 90,
) -> str:
    """Get lockup expiry schedule for a stock.

    Args:
        ticker: 6-digit A-share code
        trade_date: YYYY-MM-DD
        forward_days: how many days forward to check (default 90)

    Returns:
        Formatted text with historical unlock records and upcoming
        expiry calendar with impact metrics.
    """
    code = safe_ticker_component(ticker)
    lines = [f"# 限售解禁日历 | {code} | {trade_date}"]

    # 1. 历史解禁记录 — eastmoney datacenter direct HTTP
    try:
        history_data = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=15,
            sort_columns="FREE_DATE",
            sort_types="-1",
        )
        if history_data:
            lines.append(f"\n## 个股解禁记录 (共 {len(history_data)} 批)")
            lines.append("解禁时间 | 类型 | 解禁数量 | 占比")
            for row in history_data:
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('LIMITED_STOCK_TYPE', '')} "
                    f"| {row.get('FREE_SHARES_NUM', '')} "
                    f"| {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append("\n无历史解禁记录。")
    except Exception as e:
        lines.append(f"个股解禁查询失败: {e}")

    # 2. 未来待解禁 — eastmoney datacenter direct HTTP
    try:
        end_dt = datetime.strptime(trade_date, "%Y-%m-%d") + pd.Timedelta(days=forward_days)
        end_str = end_dt.strftime("%Y-%m-%d")
        upcoming_data = _eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=(f"(SECURITY_CODE=\"{code}\")(FREE_DATE>='{trade_date}')(FREE_DATE<='{end_str}')"),
            page_size=20,
            sort_columns="FREE_DATE",
            sort_types="1",
        )
        if upcoming_data:
            lines.append(f"\n## 未来 {forward_days} 天待解禁")
            for row in upcoming_data:
                lines.append(
                    f"  {str(row.get('FREE_DATE', ''))[:10]} "
                    f"| {row.get('LIMITED_STOCK_TYPE', '')} "
                    f"| 数量 {row.get('FREE_SHARES_NUM', '')} "
                    f"| 占比 {row.get('FREE_RATIO', '')}"
                )
        else:
            lines.append(f"\n未来 {forward_days} 天无待解禁。")
    except Exception as e:
        lines.append(f"解禁日历查询失败: {e}")

    return "\n".join(lines)
