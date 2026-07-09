"""Screening tools — hot stocks, concept blocks, announcements, industry comparison."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Annotated

from a_stock_mcp._core import (
    _CACHE_DIR,
    _UA,
    _em_get,
    _get_prefix,
    _json,
    _normalize_ticker,
    _requests,
    logger,
    random,
    safe_ticker_component,
)

# ---- 11. get_hot_stocks ----


def get_hot_stocks(
    curr_date: Annotated[str, "Date YYYY-MM-DD, empty string for today"] = "",
) -> str:
    """Get strong stocks with topic attribution from 同花顺 editorial team.

    Returns stocks that hit limit-up with human-curated reason tags
    explaining WHY they surged (e.g. '算力租赁+AI政务').
    """
    import requests

    if not curr_date or curr_date.strip() == "":
        curr_date = datetime.now().strftime("%Y-%m-%d")

    try:
        url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{curr_date}/orderby/date/orderway/desc/charset/GBK/"
        headers = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36")}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()

        if data.get("errocode", 0) != 0:
            return f"同花顺 API error: {data.get('errormsg', 'unknown')}"

        rows = data.get("data") or []
        if not rows:
            return f"No hot stocks data for {curr_date} (may be non-trading day or data not yet available)"

        lines = [
            f"# Hot Stocks with Topic Attribution ({curr_date})",
            "# Source: 同花顺 editorial (human-curated reason tags)",
            f"# Total: {len(rows)} stocks",
            "",
        ]

        from collections import Counter

        all_tags: list[str] = []

        for row in rows:
            code = row.get("code", "")
            name = row.get("name", "")
            reason = row.get("reason", "")
            zhangfu = row.get("zhangfu", "")
            huanshou = row.get("huanshou", "")
            chengjiaoe = row.get("chengjiaoe", "")
            dde = row.get("ddejingliang", "")

            lines.append(f"{code} {name}: +{zhangfu}% 换手{huanshou}% 成交额{chengjiaoe} 大单净量{dde} | {reason}")

            if reason:
                tags = [t.strip() for t in str(reason).split("+") if t.strip()]
                all_tags.extend(tags)

        if all_tags:
            cnt = Counter(all_tags)
            lines.append("\n## Theme Frequency (top 15)")
            for tag, n in cnt.most_common(15):
                lines.append(f"  {tag}: {n} stocks")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching hot stocks for {curr_date}: {str(e)}"


# ---------------------------------------------------------------------------
# Baidu PAE (百度股市通) helpers
# ---------------------------------------------------------------------------

_BAIDU_PAE_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0"),
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}


# ---- 13. get_concept_blocks ----


def get_concept_blocks(
    ticker: Annotated[str, "A-stock code (e.g. 688017)"],
) -> str:
    """Get concept/sector/region blocks that a stock belongs to (百度股市通).

    Returns industry classification (申万), concept themes, and region.
    Each block includes current day's change percentage.
    """
    import requests

    code = _normalize_ticker(ticker)

    try:
        url = (
            "https://finance.pae.baidu.com/api/getrelatedblock"
            f'?stock=[{{"code":"{code}","market":"ab","type":"stock"}}]'
            "&finClientType=pc"
        )

        # Baidu PAE 偶发 403 限流：3 次指数退避，对 403/429 单独加长退避。
        last_err: Exception | None = None
        d: dict = {}
        for attempt in range(3):
            try:
                r = requests.get(url, headers=_BAIDU_PAE_HEADERS, timeout=10)
                if r.status_code in (403, 429):
                    # rate-limited — back off harder and retry
                    wait = 1.0 * (attempt + 1)
                    logger.warning("Baidu PAE %s, retry %d/3 after %.1fs", r.status_code, attempt + 1, wait)
                    time.sleep(wait)
                    last_err = RuntimeError(f"Baidu PAE HTTP {r.status_code}")
                    continue
                r.raise_for_status()
                d = r.json()
                last_err = None
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_err = e
                wait = 0.5 * (2**attempt)  # 0.5, 1.0, 2.0
                logger.warning("Baidu PAE transient error, retry %d/3 after %.1fs: %s", attempt + 1, wait, e)
                time.sleep(wait)
        if last_err is not None:
            return f"Error fetching concept blocks for {code} (after 3 retries): {last_err}"

        if str(d.get("ResultCode", -1)) != "0":
            return f"Baidu PAE error: ResultCode={d.get('ResultCode')} {d.get('ResultMsg', '')}"

        result = d.get("Result", {})
        categories = result.get(code, [])
        if not categories:
            return f"No concept/block data for {code}"

        lines = [
            f"# Concept & Sector Blocks for {code} (A-stock)",
            "# Source: 百度股市通 (Baidu PAE)",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        concept_names: list[str] = []

        for cat in categories:
            cat_name = cat.get("name", "")
            items = cat.get("list", [])
            if not items:
                continue
            lines.append(f"## {cat_name}")
            for item in items:
                name = item.get("name", "")
                ratio = item.get("ratio", "")
                desc = item.get("describe", "")
                suffix = f" ({desc})" if desc else ""
                lines.append(f"  {name}{suffix}: {ratio}")
                if cat_name == "概念":
                    concept_names.append(name)

        if concept_names:
            lines.append(f"\nConcept tags: {' / '.join(concept_names)}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching concept blocks for {code}: {str(e)}"


# ---------------------------------------------------------------------------
# 巨潮资讯网 (cninfo) helpers — company announcements
# ---------------------------------------------------------------------------

_CNINFO_HIS_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_CNINFO_SEARCH_URL = "http://www.cninfo.com.cn/new/information/topSearch/query"
_CNINFO_STOCK_JSON_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
_CNINFO_STATIC_BASE = "http://static.cninfo.com.cn/"
_CNINFO_REFERER = "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search"
_CNINFO_HEADERS = {
    "User-Agent": _UA,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
    "Referer": _CNINFO_REFERER,
}

# Friendly category aliases → cninfo category codes (raw codes pass through).
_CNINFO_CATEGORY = {
    "all": "",
    "annual": "category_ndbg_szsh",          # 年报
    "half": "category_bndbg_szsh",           # 半年报/中报
    "quarterly_1": "category_yjdbg_szsh",    # 一季报
    "quarterly_3": "category_sjdbg_szsh",    # 三季报
    "major": "category_zdsx_szsh",           # 重大事项
    "general_meeting": "category_gddh_szsh",  # 股东大会
}

_CNINFO_SESSION = _requests.Session()
_CNINFO_SESSION.headers.update(_CNINFO_HEADERS)
_CNINFO_MIN_INTERVAL = float(os.environ.get("CNINFO_MIN_INTERVAL", "1.0"))
_cninfo_last_call = [0.0]


def _cninfo_post(url, data=None, timeout=15):
    """cninfo 统一 POST 入口：节流 + 复用 session + 瞬态重试 1 次。"""
    wait = _CNINFO_MIN_INTERVAL - (time.time() - _cninfo_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.3))
    try:
        return _CNINFO_SESSION.post(url, data=data, timeout=timeout)
    except (_requests.exceptions.ConnectionError, _requests.exceptions.ChunkedEncodingError):
        logger.warning("cninfo 请求瞬态失败，1s 后重试: %s", url)
        time.sleep(1)
        return _CNINFO_SESSION.post(url, data=data, timeout=timeout)
    finally:
        _cninfo_last_call[0] = time.time()


def _resolve_cninfo_orgid(code: str) -> str | None:
    """Resolve a 6-digit stock code to cninfo's orgId.

    Uses a disk-cached full stock map (24h TTL), with a per-query topSearch
    fallback for codes missing from the map.
    """
    cache_file = os.path.join(_CACHE_DIR, "cninfo_orgid.json")

    # Try disk cache (24h TTL)
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < 86400:
            try:
                with open(cache_file, encoding="utf-8") as f:
                    orgid_map = _json.load(f)
                if code in orgid_map:
                    return orgid_map[code]
            except (OSError, ValueError):
                pass

    # Rebuild full map from szse_stock.json (covers SH/SZ/BJ despite the name)
    orgid_map: dict[str, str] = {}
    try:
        r = _CNINFO_SESSION.get(_CNINFO_STOCK_JSON_URL, timeout=15)
        for item in r.json().get("stockList", []):
            c = item.get("code", "")
            oid = item.get("orgId", "")
            if c and oid:
                orgid_map[c] = oid
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            _json.dump(orgid_map, f, ensure_ascii=False)
        if code in orgid_map:
            return orgid_map[code]
    except Exception:
        logger.warning("Failed to build cninfo orgId map from szse_stock.json")

    # Fallback: per-query topSearch
    try:
        r = _cninfo_post(_CNINFO_SEARCH_URL, data={"keyWord": code, "maxNum": 10})
        hits = r.json().get("stockList", [])
        if hits:
            return hits[0].get("orgId")
    except Exception:
        logger.warning("cninfo topSearch fallback failed for %s", code)

    return None


# ---- 14. get_company_announcements ----


def get_company_announcements(
    ticker: Annotated[str, "A-stock code (e.g. 600519)"],
    category: Annotated[str, "category alias (all/annual/half/quarterly_1/quarterly_3/major/general_meeting)"] = "all",
    start_date: Annotated[str, "start date YYYY-MM-DD (empty = no lower bound)"] = "",
    end_date: Annotated[str, "end date YYYY-MM-DD (empty = no upper bound)"] = "",
    page_size: Annotated[int, "max announcements to return (server caps at 30)"] = 30,
) -> str:
    """Get company announcements from 巨潮资讯网 (cninfo.com.cn).

    Returns announcement title, date, type, and a direct PDF/HTML link.
    Supports category filtering (annual/half/quarterly reports, major events, etc.)
    and date range filtering.
    """
    code = _normalize_ticker(ticker)

    # Resolve orgId (required by cninfo — bare code returns 0 results)
    orgid = _resolve_cninfo_orgid(code)
    if not orgid:
        return f"Error: could not resolve cninfo orgId for {code}"

    # Map board prefix → cninfo column
    prefix = _get_prefix(code)
    column = {"sh": "sse", "sz": "szse", "bj": "bj"}.get(prefix, "szse")

    # Map category alias → code (pass through raw codes for power users)
    cat_code = _CNINFO_CATEGORY.get(category, category)

    # Build date range
    se_date = ""
    if start_date and end_date:
        se_date = f"{start_date}~{end_date}"
    elif start_date:
        se_date = f"{start_date}~"
    elif end_date:
        se_date = f"~{end_date}"

    # Server hard-caps pageSize at 30
    page_size = min(int(page_size), 30)

    try:
        form = {
            "pageNum": "1",
            "pageSize": str(page_size),
            "column": column,
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{code},{orgid}",
            "searchkey": "",
            "secid": "",
            "category": cat_code,
            "trade": "",
            "seDate": se_date,
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        r = _cninfo_post(_CNINFO_HIS_URL, data=form, timeout=15)
        d = r.json()

        anns = d.get("announcements") or []
        total = d.get("totalRecordNum", 0)

        lines = [
            f"# Company Announcements for {code} (A-stock)",
            "# Source: 巨潮资讯网 (cninfo.com.cn)",
            f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Category: {category} | Total matching: {total} | Showing: {len(anns)}",
            "",
        ]

        if not anns:
            lines.append("No announcements found for the given filters.")
            return "\n".join(lines)

        lines.append("日期 | 标题 | 类型 | 链接")
        for ann in anns:
            title = ann.get("announcementTitle", "").replace("\n", " ").strip()
            ts = ann.get("announcementTime", 0)
            date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else "N/A"
            ann_type = ann.get("announcementTypeName", "N/A")
            adjunct = ann.get("adjunctUrl", "")
            link = f"{_CNINFO_STATIC_BASE}{adjunct}" if adjunct else "N/A"
            lines.append(f"  {date_str} | {title} | {ann_type} | {link}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching announcements for {code}: {str(e)}"


# ---------------------------------------------------------------------------
# 17. Industry Comparison (行业横向对比)
# ---------------------------------------------------------------------------


def get_industry_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 20,
) -> str:
    """Get industry sector performance comparison.

    Args:
        ticker: 6-digit A-share code (used to identify relevant sector)
        trade_date: YYYY-MM-DD
        top_n: number of top/bottom industries to show (default 20)

    Returns:
        Formatted text with sector performance ranking, highlighting
        the sector the target stock belongs to.
    """
    code = safe_ticker_component(ticker)
    lines = [f"# 行业横向对比 | {code} | {trade_date}"]

    # 东财 push2 行业板块排名 (direct HTTP, replaces 同花顺 which has 401)
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
        }
        r = _em_get(url, params=params, timeout=15)
        d = r.json()
        items = d.get("data", {}).get("diff", [])

        if items:
            lines.append(f"\n## 全行业表现 (东财 {len(items)} 个行业)")
            lines.append("排名 | 行业 | 涨跌幅 | 上涨 | 下跌 | 领涨股")
            for i, item in enumerate(items):
                name = item.get("f14", "")
                change_pct = item.get("f3", 0)
                up_count = item.get("f104", 0)
                down_count = item.get("f105", 0)
                leader = item.get("f140", "")
                lines.append(f"  {i + 1}. {name} | {change_pct}% | {up_count} | {down_count} | {leader}")
                if i >= top_n * 2 - 1:
                    lines.append(f"  ... (showing top/bottom {top_n})")
                    break
        else:
            lines.append("行业数据获取为空。")
    except Exception as e:
        lines.append(f"行业对比查询失败: {e}")

    return "\n".join(lines)
