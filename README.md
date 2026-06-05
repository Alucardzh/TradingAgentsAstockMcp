# a-stock-mcp

A-share (China mainland) stock data MCP server. Standalone, zero tradingagents dependency.

## Install

```bash
cd a-stock-mcp
uv sync
```

## Run

```bash
uv run python -m a_stock_mcp.server
```

## Register MCP Server

### Claude Code

```bash
claude mcp add a-stock-data -- uv run --project D:/DevProject/TradingAgentTokenPlan/a-stock-mcp python -m a_stock_mcp.server
```

> **Windows users:** If the above command fails with argument parsing errors in CMD/PowerShell, run it from Git Bash, or register by directly editing `~/.claude.json`.

### OpenClaw / Hermes

Add the following to the project's `CLAUDE.md` (or equivalent host agent prompt):

```markdown
## MCP Servers

Use the a-stock-data MCP server for A-stock market data. Start it before invoking any analysis tools:

\`\`\`bash
uv run --project <project_root>/a-stock-mcp python -m a_stock_mcp.server
\`\`\`
```

Replace `<project_root>` with the actual project root path.

## Tools (18)

| Tool | Description |
|------|-------------|
| resolve_ticker | Chinese stock name -> 6-digit code |
| get_stock_data | OHLCV K-line data |
| get_indicators | Technical indicators (RSI, MACD, Bollinger, etc.) |
| get_fundamentals | PE/PB/market cap/financials/EPS consensus |
| get_balance_sheet | Balance sheet |
| get_cashflow | Cash flow statement |
| get_income_statement | Income statement |
| get_news | Stock-specific news |
| get_global_news | Global financial news (CLS + Eastmoney) |
| get_insider_transactions | Insider/shareholder activity |
| get_profit_forecast | Consensus EPS + forward PE/PEG |
| get_hot_stocks | Limit-up stocks with reason tags |
| get_northbound_flow | Northbound capital (沪深股通) |
| get_concept_blocks | Concept/sector block membership |
| get_fund_flow | Individual stock fund flow |
| get_dragon_tiger_board | Dragon-tiger board (龙虎榜) |
| get_lockup_expiry | Lockup expiry (限售解禁) schedule |
| get_industry_comparison | Industry sector comparison |

## Data Sources

mootdx (TCP), Tencent Finance, Eastmoney, Sina Finance, TongHuaShun, CLS, Baidu

## Environment Variables

- `ASTOCK_CACHE_DIR`: Cache directory (default: `~/.astock-mcp/cache`)
- `EM_MIN_INTERVAL`: Eastmoney rate limit interval in seconds (default: 1.0)
