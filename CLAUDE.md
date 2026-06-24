# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**领域知识必读**: 所有涉及分析计算、指标定义、行为标签的开发，必须先参考 `docs/superpowers/FINANCE_DOMAIN.md`。开发完成后按 `docs/superpowers/VERIFICATION_CHECKLIST.md` 逐项自检。

**项目经验必读**: 所有涉及交割单解析（SmartParser）、PnL/费用计算、文件上传识别的开发，必须先参考 `PROJECT_EXPERIENCE.md`（记录真实券商导出踩坑：GBK 编码、伪 `.xls` 文本、`="..."` 外壳、费用列误判、模拟数据与真实数据脱节等），避免重复踩坑。

## 项目概述

TradingJournalAnalyzer（交易日志分析器）— A 股散户上传交割单，系统重建持仓、识别行为、归因盈亏、回测策略、生成 AI 诊断报告。已进入"值得长期使用的交易复盘工具"阶段。

## 技术栈

- **前端**: Vite + React 18 + Tailwind CSS + Recharts + React Query
- **后端**: FastAPI + SQLAlchemy + Pandas
- **行情**: mootdx（通达信 TCP 7709，不封 IP）
- **AI**: OpenAI / Claude / DeepSeek（环境变量切换）
- **数据库**: PostgreSQL 17
- **认证**: JWT（邮箱/手机号注册，密码强度校验，昵称系统）
- **开发端口**: 后端 8000（默认）/ 前端 5173（默认），支持通过 vite proxy 修改

## 核心架构（6 层数据管道）

```
原始交割单 → Trade → Position → Pattern → Insight → What-If → AI 诊断报告
```

1. **Trade** — SmartParser 自动识别券商格式（基于数据值推断，不依赖列名）
2. **Position** — FIFO 持仓重建，前序持仓标记（`cost_known`），软删除支持（`is_deleted`）
3. **Pattern** — 4 维行为标签：市场环境 / 交易行为 / 交易结果 / 心理推测
4. **Insight Engine** — 按维度统计：PF、Expectancy(R)、Shapley 归因、Primary Pattern
5. **What-If Engine** — 止损回测（使用持仓期间日线 low 判断盘中触发）+ 因子贡献分析
6. **AI 解释器** — 自然语言诊断报告（V4.0 起 Prompt 携带 10+ 风险指标 + 关键交易摘要）

### V4.0 StatsResponse 新增字段

`StatsResponse`（`backend/app/schemas/analysis.py`）在 V4.0 新增两个字段：

- `equity_curve: list[EquityPoint]` — 按持仓退出日期累计盈亏的数据点序列。`EquityPoint = {date, cum_pnl, cum_pnl_pct}`。起点为 `{首笔 exit_date, 0.0, 0.0}`，后续逐笔累加。前端 `EquityCurve.tsx` 用 Recharts AreaChart 渲染。
- `symbol_summary: list[SymbolSummaryItem]` — 按个股汇总的盈亏统计。`SymbolSummaryItem = {symbol, trade_count, win_count, win_rate, total_pnl, avg_holding_days, first_trade_date, last_trade_date}`。前端 `SymbolSummaryTable.tsx` 渲染为可排序表格。

### AI Prompt 扩充（V4.0）

`build_user_prompt()`（`backend/app/ai/prompt.py`）在原有 5 字段基础上新增两个板块：

- **风险指标**：profit_factor、expectancy、max_drawdown、max_drawdown_pct、consecutive_losses、avg_mae、avg_mfe、profit_capture_ratio、total_return_pct（共 10 项）
- **关键交易**：盈利 TOP3 + 亏损 TOP3（symbol、pnl、pnl_pct、holding_days、entry_date、exit_date）

`_build_analysis_data()`（`backend/app/api/report.py`）负责从 stats 和 positions 中采集上述数据。

Validator（`backend/app/ai/validator.py`）对 PF、max_drawdown_pct、consecutive_losses 执行软校验（±1% 容忍度），不匹配仅记录 warning 不阻断。

## 关键设计决策（不可随意改动）

### 金融定义
- **所有指标对照 TradesViz/Edgewonk/Tradervue 行业标准**，详见 FINANCE_DOMAIN.md
- Expectancy 使用 R-multiple（基于 pnl_pct），不用绝对金额
- Profit Factor = gross_profit / gross_loss，不是 win_rate/(1-win_rate)
- 最大回撤必须显示百分比
- 止损回测必须检查持仓期间日线 low，不能只看最终 PnL
- BULL_TREND / BEAR_TREND 是市场环境，不是交易行为
- PYRAMID 判断加仓时是否已有持仓，不看最终 PnL
- AVERAGE_DOWN 必须验证亏损状态
- **净值曲线**（equity_curve）按持仓（Position）退出日期累计 PnL，不按逐笔成交（Trade）。起点 cum_pnl=0
- **股票维度盈亏**（symbol_summary）仅统计 cost_known=True 的有效持仓（valid_positions），与 KPI 口径一致
- **AI Prompt 风险指标**从 StatsResponse 采集，不经 AI 猜测；validator 做软校验（±1% 容忍），不阻断报告生成

### UI 规范
- **所有显示文本中文优先**，英文缩写加括号解释
- 每个指标必须加评级（优秀/良好/一般/较差）
- 信息分层：核心结果 → 进阶分析 → 高级分析（折叠）
- 小样本（<5 笔）不评价，显示"样本不足"
- 100%胜率场景：PF 显示 ∞、"最大亏损"显示 --

### 安全
- 密码强度校验：8位+含字母+含数字
- 密码传输用 POST body，禁止 GET query string
- 下载文件名校验，过滤 CRLF 防 header injection

### 性能
- `ensure_market_data()` 先查 DB 缓存，有数据就跳过 mootdx
- 并发锁防止同一 symbol 被并行拉取
- 前端渐进式加载：stats 先显示，insight/whatIf 跟随
- stats 端点首次调用时自动保存快照到 `Analysis.stats_snapshot`

## 开发命令

```bash
# 后端
cd backend
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m mootdx bestip     # 首次：初始化行情服务器列表
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pytest tests/ -q

# 前端
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

## 项目结构

```
TradingJournalAnalyzer/
├── backend/
│   ├── app/
│   │   ├── api/          # analysis, auth, report, upload
│   │   ├── engine/        # attribution, insight, mae, market_data, market_fetcher, pattern, position, whatif
│   │   ├── parsers/       # smart.py (SmartParser) + registry
│   │   ├── ai/            # provider, prompt
│   │   ├── models/        # User, RawFile, Trade, Analysis, Report, DailyBar
│   │   ├── schemas/       # auth, analysis, report
│   │   └── auth/          # JWT + password hashing
│   └── tests/
├── frontend/src/
│   ├── pages/             # Analysis, History, Landing, Login, Register, Report, Upload
│   ├── components/        # Layout, StatsCards, EquityCurve, SymbolSummaryTable, PatternChart, WhatIfChart, FileDropzone...
│   ├── api/               # client, auth, analysis, report, upload
│   ├── hooks/             # useAnalysis (React Query)
│   ├── constants/         # patterns.ts (标签中英文映射)
│   └── context/           # AuthContext
├── docs/
│   ├── superpowers/       # FINANCE_DOMAIN.md, VERIFICATION_CHECKLIST.md
│   └── review/            # 评测报告、PRD、代码审查记录
└── testfiles/             # 6 种交易风格测试交割单
```

## 标签体系（当前 V1.1+）

4 个维度，每个仓位每维度最多一个标签：

| 维度 | 标签 | 含义 |
|------|------|------|
| market_env | BULL_TREND, BEAR_TREND, BREAKDOWN | 入场所处技术环境 |
| behavior | CHASE, BOTTOM, BREAKOUT, PYRAMID, AVERAGE_DOWN, TURN, SCALP, SWING, POSITION, FOMO | 交易者主动行为 |
| outcome | TIGHT_STOP, TRAILING_STOP, TIME_EXIT, LARGE_LOSS_EXIT | 事后结果分类 |
| psychology | POSSIBLE_REVENGE, OVERTRADING, HOLD_LOSER, CUT_WINNER, PSY_FOMO | AI 推测，低置信度 |

## 数据库模型关系

```
RawFile (原始文件, filename, raw_content)
  ↓ raw_file_id
Trade (成交记录, is_deleted 软删除)
  ↓ user_id + datetime range
Analysis (分析记录, raw_file_id, stats_snapshot)
  ↓ analysis_id
Report (AI报告, report_content, analysis_input)
```

数据支持通过 `RawFile → Trade → Analysis → Report` 链路完整追溯。

## License

MIT + Commons Clause — 非商业用途开源
