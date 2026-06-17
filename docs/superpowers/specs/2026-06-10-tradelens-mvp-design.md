# TradeLens MVP 设计文档

> Version: 1.0 | Date: 2026-06-10 | Status: Approved

---

> ## ⚠️ 已归档 / SUPERSEDED（2026-06-17 标注）
>
> 本文档是 **TradeLens MVP 阶段的设计快照**（2026-06-10），保留作历史记录。项目已更名为 **TradingJournalAnalyzer** 并持续演进，
> 当前实现与本文档存在显著差异，**请勿据此理解现有系统**。
>
> *说明：本项目无发布版本/git tag，FastAPI 声明版本为 `0.1.0`；源码中散落的 `V1.x`/`V2.x` 仅为开发过程的功能里程碑注释，非产品版本号。*
>
> **当前事实来源（ authoritative ）：**
> - [CLAUDE.md](../../../CLAUDE.md) — 项目概述、技术栈、架构、目录结构
> - [FINANCE_DOMAIN.md](../FINANCE_DOMAIN.md) — 指标定义、标签边界、行业标准（开发必读）
> - [VERIFICATION_CHECKLIST.md](../VERIFICATION_CHECKLIST.md) — 开发自检清单
> - 源码本身（`backend/app/`、`frontend/src/`）
>
> ### 自 MVP 以来的关键演进（与下文冲突处以此为准）
>
> | 主题 | MVP 设计（本文档） | 当前实现 |
> |------|--------------------|----------|
> | 项目名 | TradeLens | TradingJournalAnalyzer |
> | 前端 UI 库 | shadcn/ui | Tailwind CSS（未使用 shadcn） |
> | 行情源 | a-stock-data（mootdx + 腾讯优先） | 仅 mootdx（通达信 TCP 7709），结果缓存到 `DailyBar` 表 |
> | 标签体系 | 15 个标签 / 3 模块（含 TREND、COUNTER_TREND、STOP_LOSS、TAKE_PROFIT、CASH） | **4 维度**：market_env / behavior / outcome / psychology（见 FINANCE_DOMAIN.md §二）。TREND→BULL_TREND/BEAR_TREND；STOP_LOSS/TAKE_PROFIT/CASH 移除，新增 outcome（TIGHT_STOP/TRAILING_STOP/TIME_EXIT/LARGE_LOSS_EXIT）+ psychology（5 个低置信度标签）+ behavior 增 FOMO |
> | Insight 引擎 | count/win_rate/total_pnl/avg_pnl_pct | 增加 PF、Expectancy(R)、MAE/MFE、止盈效率、Shapley 归因 |
> | What-If 引擎 | 删除某标签后重算收益 | + 止损回测（持仓期间日线 low + 跳空 min(open,stop)）+ 因子贡献分析 |
> | 数据库表 | 7 张（无 DailyBar） | 8 张（新增 `DailyBar` 行情缓存；`Analysis` 增加 `stats_snapshot`、`raw_file_id`） |
> | AI Provider | openai / claude / deepseek | + openrouter |
> | 管理后台 | 无 | 新增 `/api/admin/*`（独立鉴权，搜索用户、下载文件/分析/报告） |
> | 解析器 | 按券商一插件一文件、表头匹配 | SmartParser（基于数据值推断列，不依赖列名）+ registry |
> | 安全 | 密码 ≥6 位 | 密码 ≥8 位 + 含字母 + 含数字；软删除（`is_deleted`）；下载文件名过滤 CRLF |
>
> 下文为原始 MVP 设计，未做改动。

---

## 1. 产品概述

TradeLens — 上传交易记录（A股+期货），AI 分析亏损原因并生成改善建议。目标用户为 A 股散户和期货散户。

**核心卖点：** What If 反事实回测 — 删除特定行为后回测账户收益变化，量化每种行为对账户的伤害程度。

**核心设计原则：** AI 负责解释，程序负责计算。所有数字由 Python 计算，AI 只做自然语言文本生成。

## 2. 技术栈

| 层 | 技术 | 理由 |
|---|------|------|
| 前端 | Vite + React 18 + shadcn/ui | SPA Dashboard，极速 HMR，shadcn/ui 组件丰富 |
| 路由 | React Router v6 | 客户端路由，6 个页面 |
| 图表 | Recharts | 轻量 React 图表库，PnL 曲线/柱状图/散点图 |
| HTTP | fetch + React Query | API 请求缓存 + 自动重试 |
| Markdown | react-markdown | AI 报告渲染 |
| 后端 | FastAPI + Python | 异步支持，Pydantic 数据校验，Pandas/Polars 数据处理 |
| 行情数据 | a-stock-data (mootdx + 腾讯优先) | 零 Key 零第三方封装，mootdx/Tencent 不封 IP |
| AI | OpenAI / Claude / DeepSeek | 环境变量切换 |
| 数据库 | PostgreSQL + SQLAlchemy | 从一开始入库，为历史报告和多账户铺垫 |
| 认证 | JWT (bcrypt + python-jose) | 注册登录 |

## 3. 核心架构：6 层数据管道

```
原始交割单 → Trade → Position → Pattern → Insight Engine → What If Engine → AI 解释器 → 验证层 → 诊断报告
```

### 第 0 层：RawFile（原始文件）

永远保存原始文件，规则升级后可重新解析。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | PK |
| user_id | UUID | FK → users |
| filename | str | 原始文件名 |
| source_type | str | qmt / vnpy / dfcf / ths / wenhua / boyi / ctp / huatai / citic / guojun ... |
| asset_type | str | stock / future |
| raw_content | bytes | 原始文件内容 |
| uploaded_at | datetime | 上传时间 |

### 第 1 层：Trade（统一成交记录）

所有券商和期货终端解析后统一为此格式。股票和期货共用，期货专用字段为可选。

| 字段 | 类型 | 说明 |
|------|------|------|
| trade_id | UUID | PK |
| raw_file_id | UUID | FK → raw_files |
| user_id | UUID | FK → users |
| asset_type | enum | stock / future |
| datetime | datetime | 成交时间 |
| symbol | str | 股票代码 "600519" 或 合约代码 "rb2410" |
| exchange | str | SH / SZ / SHFE / DCE / CZCE / CFFEX |
| side | enum | BUY / SELL |
| quantity | float | A股=股, 期货=手 |
| price | float | 成交价格 |
| commission | float | 手续费 |
| margin | float? | 保证金（期货专用） |
| multiplier | int? | 合约乘数（期货专用） |

### 第 2 层：Position（持仓重建）

将离散买卖记录按 FIFO 算法重建为完整交易。后续所有分析基于 Position。

| 字段 | 类型 | 说明 |
|------|------|------|
| position_id | UUID | PK |
| user_id | UUID | FK |
| symbol | str | 代码 |
| asset_type | enum | stock / future |
| entry_date | date | 建仓日 |
| exit_date | date | 平仓日 |
| holding_days | int | 持仓天数 |
| total_quantity | float | 总买入量 |
| avg_entry_price | float | 加权平均入场价 |
| avg_exit_price | float | 加权平均出场价 |
| pnl | float | 盈亏金额 |
| pnl_pct | float | 盈亏百分比 |
| trade_ids | JSONB | 组成此 Position 的 Trade ID 列表（可溯源） |

### 第 3 层：Pattern（行为标签）

每笔 Position 可打多个标签。分三大模块：入场逻辑 + 持仓周期 + 风控/仓位管理。

| 字段 | 类型 | 说明 |
|------|------|------|
| pattern_id | UUID | PK |
| position_id | UUID | FK → positions |
| pattern_name | enum | MVP 15 个标签 |
| confidence | float | 置信度 |
| context | JSONB | 打标依据（如 `{"prev_5d_return": 0.18}`） |

**MVP 15 个标签：**

**模块一：入场行为（行情依赖 → a-stock-data）**

| 标签 | 英文 | 定义 |
|------|------|------|
| 追涨 | CHASE | 买入前 5 天涨幅 > 15% |
| 抄底 | BOTTOM | 买入前 5 天跌幅 > 15% |
| 突破 | BREAKOUT | 买入日价格创 20 日新高 |
| 趋势 | TREND | 买入时 20MA > 60MA |
| 逆势 | COUNTER_TREND | 买入时 20MA < 60MA |
| 破位 | BREAKDOWN | 卖出日价格创 20 日新低（向下突破/杀跌离场） |

**模块二：持仓周期（无行情依赖）**

| 标签 | 英文 | 定义 |
|------|------|------|
| 短线 | SCALP | 持仓 < 3 天（不含日内） |
| 波段 | SWING | 持仓 3~30 天 |
| 长持 | POSITION | 持仓 > 30 天 |

**模块三：仓位与风控行为（无行情依赖）**

| 标签 | 英文 | 定义 |
|------|------|------|
| 加仓 | PYRAMID | 同一 symbol 盈利状态下继续买入 |
| 补仓 | AVERAGE_DOWN | 同一 symbol 亏损状态下继续买入（摊薄成本） |
| 做T | TURN | 同一 symbol 当日有买有卖（日内回转，正T/反T均归此类） |
| 止损 | STOP_LOSS | 持仓亏损后主动卖出离场（pnl < 0 且非到期/交割） |
| 止盈 | TAKE_PROFIT | 持仓盈利后主动卖出离场（pnl > 0 且非到期/交割） |
| 空仓 | CASH | 该时段内无任何持仓（观望等待） |

> **V2 优化方向（MVP 不做）：** ① PYRAMID 细分为顺势加仓/等量加仓/倒金字塔；② 入场标签增加成交量维度（放量突破/无量突破）；③ 新增 INTRA_DAY（日内超短）细分 SCALP；④ 新增减仓/清仓/两融杠杆/套利/对冲等专业行为标签。

### 第 4 层：Insight Engine（归因引擎）

按 Pattern 聚合统计：count, win_count, win_rate, total_pnl, avg_pnl_pct。输出 best_pattern 和 worst_pattern。不单独存储，每次实时计算。

### 第 5 层：What If Engine（反事实回测）

对每个 Pattern，删除该模式的所有 Position 后重新计算账户总收益。输出每个 Pattern 的 original_return / what_if_return / delta / damage_score。不单独存储。

### 第 6 层：AI 解释器 + 验证层

**输入：** 结构化 JSON（所有数字已由 Insight + What If 计算完毕）

**Prompt 结构：** SYSTEM（角色约束 + 规则）+ USER（结构化 JSON + 四个分析维度）+ OUTPUT FORMAT（Markdown 格式要求）

**验证层：** AI 输出后，正则提取报告中的数字，与输入 JSON 对比。偏差超 1% 则重试，最多 3 次。3 次仍失败标记 validation_failed。

**Provider 抽象：** 环境变量 `AI_PROVIDER` 控制（openai / claude / deepseek），factory 函数获取对应实现。

## 4. 解析器插件架构

### 统一接口

```python
class BaseParser(ABC):
    @classmethod
    @abstractmethod
    def source_type(cls) -> str: ...
    @classmethod
    @abstractmethod
    def asset_type(cls) -> str: ...
    @classmethod
    @abstractmethod
    def detect(cls, file: UploadedFile) -> float: ...
    @classmethod
    @abstractmethod
    def parse(cls, file: UploadedFile, raw_file_id, user_id) -> list[Trade]: ...
```

### ParserRegistry

- `auto_discover()` — 扫描 parsers/ 目录自动注册
- `detect_format(file)` — 返回所有匹配的 (source_type, confidence)，按置信度降序
- 阈值 0.7 — 无解析器达标时返回候选列表让用户手动选
- detect() 策略：纯表头匹配，不靠文件名和魔数

### 支持格式（15+）

| 类别 | 来源 |
|------|------|
| A 股 API 终端 | QMT、VN.PY、东方财富、同花顺 |
| 期货终端 | 文华财经、博易大师、快期/易盛/CTP |
| 传统券商 APP | 华泰涨乐、中信信e投、国君君弘、广发易淘金、海通e海通财… |

## 5. API 设计

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/register | 注册（email + password） |
| POST | /api/auth/login | 登录 → JWT |

### 上传 & 解析（三步走）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/upload | 上传文件 → 保存 RawFile → 格式检测 → 返回候选 |
| POST | /api/upload/confirm | 用户确认格式 → 解析 → 返回 Trade 预览 |
| POST | /api/upload/import | 确认无误 → Trade[] 入库 → 返回摘要 |

### 分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/analysis/run | 执行完整管道 → 返回 analysis_id |
| GET | /api/analysis/{id}/stats | 交易统计 |
| GET | /api/analysis/{id}/insight | 行为归因 |
| GET | /api/analysis/{id}/whatif | What If 回测 |

### 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/report/generate | AI 生成报告 → 验证 → 返回 |
| GET | /api/report/{id} | 查看已生成报告 |
| GET | /api/reports | 历史报告列表 |

## 6. 数据库 Schema

**7 张表：** users → raw_files → trades → positions → patterns → analyses → reports

**analyses 表**（轻量元数据，计算结果不存，每次实时从 trades/positions/patterns 重算）：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | PK，对应 API 中的 analysis_id |
| user_id | UUID | FK → users |
| date_start | date | 分析起始日期 |
| date_end | date | 分析截止日期 |
| created_at | datetime | 分析时间 |

其余 6 张表结构见上方各层定义。

**索引策略：**
- users: (email UNIQUE)
- trades: (user_id, datetime), (user_id, symbol, datetime)
- positions: (user_id, entry_date)
- patterns: (position_id)
- raw_files: (user_id, uploaded_at)
- analyses: (user_id, created_at)
- reports: (user_id, created_at)

## 7. 前端路由

| 路由 | 页面 | 说明 |
|------|------|------|
| / | Landing | 产品介绍 + CTA |
| /login | Login | 登录 |
| /register | Register | 注册 |
| /upload | Upload | 三步向导（拖拽 → 确认格式 → 预览导入） |
| /analysis/:id | Dashboard | 三 Tab（统计 / 行为归因 / What If 回测） |
| /report/:id | Report | AI 诊断报告 Markdown 渲染 |
| /history | History | 历史报告列表 |

**状态管理：** React Context + useReducer（MVP 无需 Redux）

## 8. 项目结构（预期）

```
TradingJournalAnalyzer/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 环境变量配置
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic 请求/响应
│   │   ├── api/                 # 路由（auth, upload, analysis, report）
│   │   ├── parsers/             # 解析器插件（qmt.py, vnpy.py, dfcf.py...）
│   │   ├── engine/              # 计算引擎（position, pattern, insight, whatif）
│   │   ├── ai/                  # AI 层（prompt, llm_provider, validator）
│   │   └── auth/                # JWT 认证
│   ├── tests/
│   ├── requirements.txt
│   └── alembic/                 # 数据库迁移
├── frontend/
│   ├── src/
│   │   ├── pages/               # Landing, Login, Register, Upload, Analysis, Report, History
│   │   ├── components/          # shadcn/ui + 自定义组件
│   │   ├── hooks/               # useAuth, useAnalysis, useReport
│   │   ├── api/                 # fetch 封装
│   │   └── context/             # AuthContext
│   ├── package.json
│   └── vite.config.ts
├── docs/
│   └── superpowers/specs/
├── CLAUDE.md
├── 交易日志分析器.md
└── 交易日志分析器补充说明.md
```

## 9. MVP 范围 vs 延后

### MVP 包含（2 周）

- 注册/登录（JWT）
- 上传交割单（CSV/Excel），拖拽，自动识别格式
- 15+ 券商/终端格式支持
- Position 重建（FIFO）
- 15 个行为标签（6 个行情依赖 + 9 个无依赖，通过 a-stock-data）
- 交易统计 KPI（总次数、胜率、盈亏比、最大盈/亏、平均持仓天数、连续亏损次数）
- Insight 归因（best/worst pattern）
- What If 回测（删除每种行为后的收益变化）
- AI 生成一句话核心结论 + 四维度诊断报告
- 验证层（AI 输出数字校验）
- 报告 Markdown 渲染

### MVP 不包含

- PDF 导出
- 用户可自行选择 AI 提供商
- 多账户管理
- 交易人格分析
- Shadow Account
- 报告分享功能
- 收费/Payment 系统
- iwencai 语义搜索（需要 API Key）

## 10. 关键风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| AI 生成不准确的数字 | 验证层提取数字与输入 JSON 对比，偏差超 1% 重试 |
| 东财 API 风控封 IP | 优先用 mootdx/腾讯（不封 IP），东财统一走 em_get() 限流 |
| 格式识别准确率不足 | detect() 阈值 0.7，低置信度让用户手动选择兜底 |
| Position 重建边缘情况 | trade_ids 可溯源，规则升级后可重新解析 |
| a-stock-data 依赖稳定性 | 零第三方封装，直连 HTTP API，可自行维护 |
