# TradeDoctor — 交易诊断助手

上传交割单，系统自动重建持仓、识别交易行为、分析盈亏来源。面向 A 股散户的交易行为诊断工具。

**核心能力**：FIFO 持仓重建 + 4 维行为标签 + MAE/MFE 风险分析 + Shapley 归因 + What-If 止损回测 + 净值曲线 + 股票维度盈亏 + AI 诊断报告（含 10+ 风险指标）。

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vite + React 18 + Tailwind CSS + Recharts + React Query |
| 后端 | FastAPI + SQLAlchemy + Pandas |
| AI | OpenAI / Claude / DeepSeek（环境变量切换） |
| 数据库 | PostgreSQL 17 |
| 行情数据 | mootdx（通达信 TCP 7709，不封 IP） |

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- PostgreSQL 17

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 创建数据库
psql -U postgres -c "CREATE DATABASE tradelens;"

# 配置环境变量（从模板复制后修改）
cp .env.example .env
# 编辑 .env，至少设置 DATABASE_URL 和 SECRET_KEY

# 初始化行情数据服务器
python -m mootdx bestip

# 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**环境变量**：后端启动前必须配置 `backend/.env`。从 `.env.example` 复制后修改：

| 变量 | 必填 | 说明 |
|------|------|------|
| `DATABASE_URL` | 是 | PostgreSQL 连接串 |
| `SECRET_KEY` | 是 | JWT 签名密钥，生产环境须 >=32 字符 |
| `AI_PROVIDER` | 否 | AI 提供商：openai / claude / deepseek（默认 openai） |
| `OPENAI_API_KEY` | 否 | OpenAI API 密钥（使用 AI 诊断报告时需要） |
| `ENV` | 否 | 设为 `production` 时启用严格安全校验 |

完整变量列表见 `backend/.env.example`。

### 前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173

### 运行测试

```bash
cd backend && pytest tests/ -q
```

## 核心架构：6 层数据管道

```
原始交割单 → Trade → Position → Pattern → Insight → What-If → AI 诊断报告
```

1. **Trade** — SmartParser 自动识别券商格式（不看列名，看数据值）
2. **Position** — FIFO 持仓重建，前序持仓标记（`cost_known`）
3. **Pattern** — 4 维行为标签（市场环境 / 交易行为 / 交易结果 / 心理推测）
4. **Insight Engine** — 按维度分别统计：胜率、PF、Expectancy、Shapley 归因
5. **What-If Engine** — 止损规则回测（持仓期间日线 low 判断触发）+ 因子贡献分析
6. **AI 解释器** — 自然语言诊断报告

## 分析指标（对照 TradesViz / Edgewonk / Tradervue）

| 指标 | 说明 |
|------|------|
| 总盈亏 + 收益率 | 绝对金额 + 总收益率% |
| 胜率 | 盈利笔数 ÷ 总笔数 |
| 最大回撤 | 百分比（行业标准），含绝对金额参考 |
| 盈亏比（Profit Factor） | 总盈利 ÷ 总亏损，>1.5 合格 |
| 预期收益（Expectancy） | R-multiple，每笔交易预期收益率 |
| 损益比（Payoff Ratio） | 平均盈利 ÷ 平均亏损 |
| 最大回撤容忍度（MAE） | 持仓期间平均最大浮亏% |
| 最大浮盈（MFE） | 持仓期间平均最高盈利% |
| 止盈效率（Profit Capture） | 浮盈兑现率 |
| Shapley 归因 | 公平归因各标签对总盈亏的贡献 |
| 净值曲线 | 按持仓退出日期累计盈亏的面积图，盈利绿色/亏损红色 |
| 股票维度盈亏 | 按个股汇总交易次数、胜率、总盈亏、平均持仓天数 |

## 4 维行为标签体系

| 维度 | 标签 | 说明 |
|------|------|------|
| **市场环境** | BULL_TREND, BEAR_TREND, BREAKDOWN | 入场所处技术环境（客观） |
| **交易行为** | CHASE, BOTTOM, BREAKOUT, PYRAMID, AVERAGE_DOWN, TURN, SCALP, SWING, POSITION, FOMO | 交易者主动采取的动作 |
| **交易结果** | TIGHT_STOP, TRAILING_STOP, TIME_EXIT, LARGE_LOSS_EXIT | 事后结果分类 |
| **心理推测** | POSSIBLE_REVENGE, OVERTRADING, HOLD_LOSER, CUT_WINNER, PSY_FOMO | AI 推测（低置信度） |

## 支持的券商/终端

| 类别 | 来源 |
|------|------|
| A 股 API 终端 | QMT、VN.PY、东方财富、同花顺 |
| 期货终端 | 文华财经、博易大师、CTP/快期/易盛 |
| 券商 APP | 华泰涨乐、中信信e投、国君君弘、广发易淘金、海通e海通财… |
| **通用** | SmartParser（基于数据值推断，零配置） |

## 项目结构

```
TradeDoctor/
├── backend/
│   ├── app/
│   │   ├── api/          # REST 端点 (auth, upload, analysis, report)
│   │   ├── engine/        # 计算引擎 (position, pattern, insight, whatif, mae, attribution)
│   │   ├── parsers/       # 解析器 (smart.py + 券商插件)
│   │   ├── ai/            # AI 层 (provider, prompt)
│   │   ├── models/        # SQLAlchemy 模型
│   │   └── auth/          # JWT 认证
│   └── tests/             # 单元测试 + 引擎测试
├── frontend/
│   └── src/
│       ├── pages/         # upload, analysis, report, history, auth
│       ├── components/    # StatsCards, EquityCurve, SymbolSummaryTable, PatternChart, WhatIfChart
│       └── constants/     # patterns.ts（标签中英文映射）
├── docs/
│   ├── superpowers/       # 金融领域知识 + 验证清单
│   └── review/            # 评测报告、PRD、代码审查记录
└── testfiles/             # 测试用交割单（6 种交易风格）
```

## 设计原则

- **AI 负责解释，程序负责计算** — 所有数字由 Python 计算，AI 仅生成自然语言报告
- **中文优先** — 所有指标显示中文术语，英文缩写加括号解释
- **散户可理解** — 每个指标附评级（优秀/良好/一般/较差）和一行解释
- **信息分层** — 核心结果 → 进阶分析 → 高级分析（折叠）
- **领域知识驱动** — 开发前参考 `docs/superpowers/FINANCE_DOMAIN.md`，完成后按 `docs/superpowers/VERIFICATION_CHECKLIST.md` 自检

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| V1.2.5 | 2026-07-01 | 架构债修复：report.py 改读 stats_snapshot、消除慢路径与 compute.py ~280 行重复、统一 PATTERN_MODULES 映射（P0-1/P1-1/P1-2） |
| V1.2.4 | 2026-07-01 | 审计核实修复：CHASE/FOMO 主动行为标签被持仓分类覆盖（conf 降级）+ insight/whatif 慢路径 self-heal 写快照 |
| V1.2.3 | 2026-06-30 | What-If 新增移动止损/固定止盈/移动止盈三规则 + 固定止损 5%→8% + T+1 修正 + AI 报告 scenario_backtest 段 |
| V1.2.2 | 2026-06-30 | 展示层归因语义修复：WhatIf 改用 delta 反事实方向、新增大亏止损模拟、回撤/期望/小样本文案修正 |
| V1.2.1 | 2026-06-30 | 前端 P1+P2：导航/KPI/报告 TOC/响应式/A11y/可选昵称/管理员加固 + vitest 19 项 + Playwright E2E 16 项 |
| V1.2.0 | 2026-06-29 | AI 报告反事实方向修复 + 补 avg_pnl_pct/shapley 等输入字段 + 建立《AI 输入字段契约》 |
| V1.1.3 | 2026-06-29 | 路由补齐+登录回跳、黄色警告可折叠、股票中文名+移动端卡片视图、注册/登录一致性 |
| V1.1.2 | 2026-06-28 | 最大回撤百分比 >100% 修复、best/worst pattern 误判修复、Shapley 百分比符号取反修复 |
| V1.1.0 | 2026-06-27 | 深度代码审查：422 数据丢失根因（快照不一致）+ 63 个测试补全 + 死代码清理 |
| V1.0.0 | 2026-06-26 | 首个正式版本：完整分析链路 + 匿名案例贡献 + ConsentLog 合规审计 |

## License

MIT + Commons Clause — 非商业用途开源
