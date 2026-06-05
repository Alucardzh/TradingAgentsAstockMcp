# a-stock-mcp

A股（中国沪深京交易所）行情数据 MCP 服务器，为 AI 编程代理提供一站式股票数据。
独立运行，零框架依赖。

## 特性

- **18 个 MCP 工具** — 从 K 线行情到龙虎榜，覆盖行情、基本面、新闻、资金流等全场景
- **多数据源自动降级** — 以 mootdx TCP 为主，Sina/腾讯/东方财富/同花顺/百度/财联社自动兜底
- **内置防封限速** — 东方财富请求走单点节流（可配最小间隔 + 随机抖动）
- **智能代码解析** — 支持中文名（"贵州茅台"）、前缀（SH600519）、后缀（600519.SH）等多种格式
- **本地缓存** — K 线按股票缓存 CSV；北向资金通过每日快照自建历史

## 快速开始

### 前置条件

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装

```bash
git clone https://github.com/Alucardzh/TraderAgentAstockMcp.git && cd TraderAgentAstockMcp
uv sync
```

### 运行

```bash
uv run python -m a_stock_mcp.server
```

或使用注册入口：

```bash
uv run a-stock-mcp
```

## 注册到 AI 代理

### Claude Code

```bash
claude mcp add a-stock-data -- uv run --project /path/to/TraderAgentAstockMcp python -m a_stock_mcp.server
```

> **Windows 用户：** 若在 CMD/PowerShell 中执行报错，请改用 Git Bash 运行，或直接编辑 `~/.claude.json`。

### OpenClaw / Hermes

向代理发送以下 prompt：

```
请 git clone https://github.com/Alucardzh/TraderAgentAstockMcp 到合适的位置，然后添加此项目的 MCP 服务。
```

## 工具一览（18 个）

### 行情数据

| 工具 | 说明 |
|------|------|
| `resolve_ticker` | 将中文名或各种代码格式解析为标准 6 位代码 |
| `get_stock_data` | OHLCV 日 K 线数据（最多 800 根） |
| `get_indicators` | 技术指标：SMA、EMA、MACD、RSI、布林带、ATR、VWMA、MFI 等（共 14 种） |

### 基本面 & 财务

| 工具 | 说明 |
|------|------|
| `get_fundamentals` | PE/PB/市值/营收/EPS + 一致预期 EPS + 远期 PE/PEG |
| `get_balance_sheet` | 资产负债表（季度/年度） |
| `get_cashflow` | 现金流量表（季度/年度） |
| `get_income_statement` | 利润表（季度/年度） |
| `get_profit_forecast` | 分析师一致预期 EPS、远期 PE、PEG、PE 消化时间 |
| `get_insider_transactions` | 股东研究 / 内部人士交易 |

### 新闻 & 情绪

| 工具 | 说明 |
|------|------|
| `get_news` | 个股相关新闻 |
| `get_global_news` | 国内/全球财经新闻（财联社 + 东方财富 7x24） |
| `get_hot_stocks` | 涨停股 + 人工标注涨停原因 + 题材频次分析 |

### 资金流向

| 工具 | 说明 |
|------|------|
| `get_northbound_flow` | 北向资金（沪深股通）分钟级实时 + 20 日历史 |
| `get_fund_flow` | 分钟级主力/大/中/小/超大单净流入 |
| `get_dragon_tiger_board` | 龙虎榜上榜记录、买卖席位、机构动向 |

### 板块 & 日程

| 工具 | 说明 |
|------|------|
| `get_concept_blocks` | 申万行业 / 概念题材 / 地域板块 + 当日涨跌 |
| `get_industry_comparison` | 同花顺全 ~90 个行业板块排名 |
| `get_lockup_expiry` | 限售解禁日程 + 未来解禁日历 |

## 数据源

| 数据源 | 协议 | 用途 |
|--------|------|------|
| mootdx（通达信） | TCP | K 线、名称代码映射、F10 股东数据 |
| 新浪财经 | HTTP | K 线备用、财务报表 |
| 腾讯财经 | HTTP | PE/PB/市值 |
| 东方财富 | HTTP | 新闻搜索、资金流、龙虎榜、解禁、行业排名 |
| 同花顺 | HTTP | 盈利预测、涨停股、北向资金 |
| 财联社 | HTTP | 实时财经新闻电报 |
| 百度股市通 | HTTP | 概念/板块归属 |

## 配置

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ASTOCK_CACHE_DIR` | `~/.astock-mcp/cache` | K 线 CSV 缓存和北向资金日缓存目录 |
| `EM_MIN_INTERVAL` | `1.0`（秒） | 东方财富 API 最小请求间隔。多代理批量场景建议调至 1.5–2.0 |

## 开发

```bash
# 安装开发依赖
uv sync --dev

# 代码检查 & 格式化
uv run ruff check .
uv run ruff format .

# 类型检查
uv run mypy src/

# 运行测试
uv run pytest
```

## 许可证

[Apache License 2.0](LICENSE)

## English Documentation

[README.md](README.md)
