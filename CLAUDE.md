# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**领域知识必读**: 所有涉及分析计算、指标定义、行为标签的开发，必须先参考 `docs/superpowers/FINANCE_DOMAIN.md`。开发完成后按 `docs/superpowers/VERIFICATION_CHECKLIST.md` 逐项自检。

## 项目概述

TradingJournalAnalyzer（交易日志分析器）— A 股散户上传交割单，系统重建持仓、识别行为、归因盈亏、回测策略、生成 AI 诊断报告。已进入"值得长期使用的交易复盘工具"阶段。

## 技术栈

- **前端**: Vite + React 18 + Tailwind CSS + Recharts + React Query
- **后端**: FastAPI + SQLAlchemy + Pandas
- **行情**: mootdx（通达信 TCP 7709，不封 IP）
- **AI**: OpenAI / Claude / DeepSeek（环境变量切换）
- **数据库**: PostgreSQL 17
- **认证**: JWT（邮箱/手机号注册，密码强度校验，昵称系统）

## 核心架构（6 层数据管道）

```
原始交割单 → Trade → Position → Pattern → Insight → What-If → AI 诊断报告
```

1. **Trade** — SmartParser 自动识别券商格式（基于数据值推断，不依赖列名）
2. **Position** — FIFO 持仓重建，前序持仓标记（`cost_known`），软删除支持（`is_deleted`）
3. **Pattern** — 4 维行为标签：市场环境 / 交易行为 / 交易结果 / 心理推测
4. **Insight Engine** — 按维度统计：PF、Expectancy(R)、Shapley 归因、Primary Pattern
5. **What-If Engine** — 止损回测（使用持仓期间日线 low 判断盘中触发）+ 因子贡献分析
6. **AI 解释器** — 自然语言诊断报告

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
- 清空数据 = 软删除（`is_deleted=True`），不丢失原始数据

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

# 管理员页面
http://localhost:5173/admin  # admin@admin.com / admin2026#
```

## 项目结构

```
TradingJournalAnalyzer/
├── backend/
│   ├── app/
│   │   ├── api/          # admin, analysis, auth, report, upload
│   │   ├── engine/        # attribution, insight, mae, market_data, market_fetcher, pattern, position, whatif
│   │   ├── parsers/       # smart.py (SmartParser) + registry
│   │   ├── ai/            # provider, prompt
│   │   ├── models/        # User, RawFile, Trade, Analysis, Report, DailyBar
│   │   ├── schemas/       # auth, analysis, report
│   │   └── auth/          # JWT + password hashing
│   └── tests/
├── frontend/src/
│   ├── pages/             # Admin, Analysis, History, Landing, Login, Register, Report, Upload
│   ├── components/        # Layout, StatsCards, PatternChart, WhatIfChart, FileDropzone...
│   ├── api/               # client, auth, analysis, report, upload
│   ├── hooks/             # useAnalysis (React Query)
│   ├── constants/         # patterns.ts (标签中英文映射)
│   └── context/           # AuthContext
├── docs/
│   └── superpowers/       # FINANCE_DOMAIN.md, VERIFICATION_CHECKLIST.md
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

管理员可通过 `RawFile → Trade → Analysis → Report` 完整链路检索用户数据。

## License

MIT + Commons Clause — 非商业用途开源
