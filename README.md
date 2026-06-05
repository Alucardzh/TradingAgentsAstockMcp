# a-stock-mcp

A-share (China mainland) stock market data MCP server for AI coding agents.
Standalone, zero framework dependency.

## Features

- **18 MCP tools** — from K-line data to dragon-tiger board, covering market data, fundamentals, news, capital flow, and more
- **Multi-source with auto-fallback** — mootdx TCP (primary), Sina/Tencent/Eastmoney/THS/Baidu/CLS as backup
- **Anti-ban built-in** — Eastmoney requests are rate-limited with configurable minimum interval + random jitter
- **Smart ticker resolution** — accepts Chinese names (e.g. "贵州茅台"), codes with prefixes (SH600519), or suffixes (600519.SH)
- **Local caching** — OHLCV data cached per ticker; northbound flow self-builds history via daily snapshots

## Quick Start

### Prerequisites

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) package manager

### Install

```bash
git clone https://github.com/Alucardzh/TraderAgentAstockMcp.git && cd TraderAgentAstockMcp
uv sync
```

### Run

```bash
uv run python -m a_stock_mcp.server
```

Or use the registered entry point:

```bash
uv run a-stock-mcp
```

## Register with AI Agents

### Claude Code

```bash
claude mcp add a-stock-data -- uv run --project /path/to/TraderAgentAstockMcp python -m a_stock_mcp.server
```

> **Windows users:** If the above fails in CMD/PowerShell, run it from Git Bash or edit `~/.claude.json` directly.

### OpenClaw / Hermes

Send the following prompt to the agent:

```
请 git clone https://github.com/Alucardzh/TraderAgentAstockMcp 到合适的位置，然后添加此项目的 MCP 服务。
```

## Tools Reference (18)

### Market Data

| Tool | Description |
|------|-------------|
| `resolve_ticker` | Resolve Chinese stock name or various code formats to a normalized 6-digit code |
| `get_stock_data` | OHLCV daily K-line data (up to 800 bars) |
| `get_indicators` | Technical indicators: SMA, EMA, MACD, RSI, Bollinger, ATR, VWMA, MFI, etc. (14 total) |

### Fundamentals & Financials

| Tool | Description |
|------|-------------|
| `get_fundamentals` | PE/PB/market cap/revenue/EPS + consensus EPS forecast + forward PE/PEG |
| `get_balance_sheet` | Balance sheet (quarterly or annual) |
| `get_cashflow` | Cash flow statement (quarterly or annual) |
| `get_income_statement` | Income statement (quarterly or annual) |
| `get_profit_forecast` | Analyst consensus EPS, forward PE, PEG, PE digestion |
| `get_insider_transactions` | Shareholder research / insider activity |

### News & Sentiment

| Tool | Description |
|------|-------------|
| `get_news` | Stock-specific news articles |
| `get_global_news` | China/global financial news (CLS + Eastmoney 7x24) |
| `get_hot_stocks` | Limit-up stocks with curated reason tags + theme frequency |

### Capital Flow

| Tool | Description |
|------|-------------|
| `get_northbound_flow` | Northbound capital (沪深股通) with minute-level realtime + 20-day history |
| `get_fund_flow` | Minute-level main/large/medium/small/super order net inflow |
| `get_dragon_tiger_board` | Dragon-tiger board (龙虎榜) with top buyer/seller seats |

### Sector & Schedule

| Tool | Description |
|------|-------------|
| `get_concept_blocks` | Industry (申万) / concept themes / region blocks with daily changes |
| `get_industry_comparison` | All ~90 THS industries ranked by performance |
| `get_lockup_expiry` | Lockup expiry (限售解禁) schedule with upcoming calendar |

## Data Sources

| Source | Protocol | Usage |
|--------|----------|-------|
| mootdx (通达信) | TCP | K-line data, name-code map, F10 insider data |
| Sina Finance | HTTP | K-line fallback, financial statements |
| Tencent Finance | HTTP | PE/PB/market cap |
| Eastmoney | HTTP | News search, fund flow, dragon-tiger, lockup, industry ranking |
| TongHuaShun (同花顺) | HTTP | Profit forecast, hot stocks, northbound flow |
| CLS (财联社) | HTTP | Real-time financial news wire |
| Baidu PAE | HTTP | Concept/sector block membership |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ASTOCK_CACHE_DIR` | `~/.astock-mcp/cache` | Directory for OHLCV CSV cache and northbound daily cache |
| `EM_MIN_INTERVAL` | `1.0` (seconds) | Minimum interval between Eastmoney API requests. Increase to 1.5–2.0 for multi-agent batch scenarios |

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Lint & format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src/

# Run tests
uv run pytest
```

## Acknowledgements

The project idea and part of the code are derived from [TradingAgents-astock](https://github.com/simonlin1212/TradingAgents-astock). If you find this project useful, please go give the original repo a star.

## License

[Apache License 2.0](LICENSE)

## 中文文档

[README_CN.md](README_CN.md)
