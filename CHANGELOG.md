# 变更日志

本项目所有重要变更记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [V1.2.5] — 2026-07-01

### 概述

V1.2.4 审计核实修复后，ecc:architect 做了架构审查，发现 3 个问题（P0-1/P1-1/P1-2，均经我独立核实属实）。本轮彻底修复——消除慢路径与 compute.py 的重复、report.py 改读 stats_snapshot、统一标签映射定义。`test_compute_equivalence.py` drift 防护网全程锁定等价性。

### 修复的 Bug

#### 1. P0-1：report.py 的 max_drawdown_pct 与 stats 面板不一致（阻断，既有 bug）

**现象**：`report.py:354` 内联重算 max_drawdown_pct 用旧公式 `dd_denom = peak`，而 `compute.py`/`analysis.py` 已在 V1.1.2 修复为 `dd_denom = total_invested + peak`（回撤穿越零值时 >100%）。AI 诊断报告的回撤百分比与 stats 面板不一致——测试数据下 report=2.0531（>100%）vs stats=0.0479。AI 据此评级会与用户肉眼打架。

**根因**：`report.py` 内联重算 stats ~60 行（债务 E），V1.1.2 修 stats 时漏改这份副本。这是慢路径与 compute.py 重复（债务 A）的直接产物。

**修复**：`generate_report` 改读 `analysis.stats_snapshot`（与 /stats 端点同源），无快照才回退 `compute_stats`。删除 ~60 行内联重算。护栏字段（is_small_sample / avg_*_holding_days）不在 snapshot 里，合并进去。

#### 2. P1-1：慢路径与 compute.py 重复（债务 A 根治）

**现象**：`analysis.py` 三个 GET 慢路径（get_stats/insight/whatif）与 `compute.py` 手工副本 ~280 行（V1.2.4 补 self-heal 后 ~320 行），self-heal 块在 4 处重复。P0-1 就是这个重复的产物——任何 compute.py 算法调整都必须手工同步到 3 个端点，遗漏即漂移。

**修复**：
- 抽取 `compute.persist_snapshot(db, analysis, field, payload)` 公共方法，统一 self-heal（commit + rollback 防御）
- `get_stats` 慢路径复用 `compute_stats` + patch MAE/MFE（compute_stats 硬编码 0，仿 compute_all backfill）
- `get_insight` 慢路径复用 `compute_insight` + `_build_category_map`
- `get_whatif` 慢路径复用 `compute_whatif`
- 删除 analysis.py 本地 `_build_category_map`、`_compute_consecutive_losses`（与 compute.py 等价）
- 慢路径仍用串行 `ensure_market_data`（非并行 fetcher），保留 V1.1.0 记录的 session 安全设计

**收益**：~280 行重复消除，未来 compute.py 算法调整自动传播到所有端点，P0 类漂移从结构性必然变为不可能。

#### 3. P1-2：PATTERN_MODULES 三处定义（债务）

**现象**：标签→维度映射在 `pattern.py`（CATEGORY_MAP）、`analysis.py`（PATTERN_MODULES）、`compute.py`（PATTERN_MODULES）三处定义，靠人工同步。新增标签时遗漏会导致 `_module_for_pattern` 返回默认值，标签被错误归类。

**修复**：删除 analysis.py/compute.py 的 PATTERN_MODULES 副本，`_module_for_pattern` 改用 `PatternEngine.CATEGORY_MAP.get(name, "behavior")`。CATEGORY_MAP 成为单一来源。

### 验证

- TDD：每个修复点先红后绿（P1-2 的 3 测试、P1-1 的 2 测试、P0-1 的 1 测试）
- drift 防护网 `test_compute_equivalence.py`：慢路径 == compute_all 三组等价性测试全绿（重构前后均绿，证明无漂移）
- 后端全套：**428 passed / 0 failed**（V1.2.4 基线 422 + 新增 6）

### 涉及文件

- 后端：`backend/app/engine/compute.py`（+`persist_snapshot`、删 PATTERN_MODULES）、`backend/app/api/analysis.py`（三慢路径复用 compute_*、删本地副本）、`backend/app/api/report.py`（读 stats_snapshot、删 ~60 行内联重算）
- 测试：`backend/tests/test_engine/test_pattern.py`（+3）、`backend/tests/test_engine/test_compute_equivalence.py`（+2、更新 docstring）、`backend/tests/test_api/test_report.py`（+1）

### 不做（YAGNI）

- P2-1（confidence → 显式优先级表）、P2-2（get_whatif rule_type 死参数）、P3（别名/重复函数清理）— 与本次无关，留待未来

---

## [V1.2.4] — 2026-07-01

### 概述

针对《中信交割单独立复算审计报告_20260630》列出的 6 个疑似 bug，本轮以**完全独立于项目代码**的复算（pandas + psycopg2 从 `trades_raw.json` + `daily_bars` 表出发，自实现 FIFO/标签/WhatIf）逐项核实。结论：**6 个里只有 2 个属实**——审计员上轮已误判过"313 vs 307 漏 6 笔"，本轮再次出现多处误判，独立复算是唯一可靠的核实手段。

### 核实结论（独立复算 vs 审计员 vs 系统 三方对比）

| Bug | 审计员判定 | 独立复算判定 | 根因 |
|-----|-----------|-------------|------|
| BUG-1 CHASE/FOMO 缺失 | 属实(高) | **✅ 属实** | `resolve_per_category` 中 CHASE/FOMO(conf=0.7) 被 SCALP/SWING/POSITION(conf=1.0) 覆盖。独立按 FINANCE_DOMAIN.md 三条件复算 CHASE=23/FOMO=22，系统=0 |
| BUG-2 HOLD/CUT 过标 | 属实(高) | ❌ 不属实 | 代码逐仓位实现合理（独立复算 HOLD=21/CUT=30 ≈ 系统 27/26）。审计员误以为应"整体标1次" |
| BUG-3 快照 null | 属实(P0) | ⚠️ 属实但非P0 | `get_insight`/`get_whatif` 慢路径不写快照，慢路径能成功返回，是性能问题非阻断 |
| BUG-4 止损 delta 反转 | 属实(高) | ❌ 不属实 | 含双边 commission 独立复算 delta 与系统一致（-0.0003/-0.0008）。审计员漏扣 commission 导致 delta 偏正 |
| BUG-5 移动止盈偏小 | 属实(高) | ❌ 不属实 | 含 commission 独立复算 +0.0073 ≈ 系统 +0.0083。审计员漏 commission 导致 +0.0404 偏大5倍 |
| BUG-6 TIME_EXIT 少标 | 属实(中) | ❌ 不属实 | 4 个候选里 3 个盈利的被 TRAILING_STOP(同 conf=0.6 先加入)覆盖，只剩1个亏损的标 TIME_EXIT，系统行为正确 |

### 修复的 Bug

#### 1. BUG-1：主动行为标签被持仓分类覆盖（高）

**现象**：系统对真实交割单产出 behavior 维度 CHASE=0、FOMO=0，独立复算应有 CHASE=23、FOMO=22。所有"交易者主动行为"标签（CHASE/FOMO/PYRAMID/AVERAGE_DOWN/TURN/BOTTOM）被必然存在的"持仓时长分类"标签（SCALP/SWING/POSITION）覆盖，behavior 维度只剩持仓时长分类，主动行为诊断信息全部丢失。

**根因**：`pattern.py:tag_position` 给 SCALP/SWING/POSITION 打 confidence=1.0，而 CHASE/FOMO 等主动行为 conf≤1.0。`resolve_per_category` 在 behavior 维度取 confidence 最高者 → 持仓分类永远胜出。代码行 306 注释给 TURN 加 conf=1.0 boost 证明开发者已知此问题，但 CHASE/FOMO 没加。

**修复**：把 SCALP/SWING/POSITION 的 confidence 从 1.0 降到 0.5（它们是必然的持仓分类，`holding_days` 字段已单独保存时长信息，降级不丢信息）。主动行为 0.7-1.0 自然胜出；纯持仓分类间仍互斥。

**验证**：真实 daily_bars 复算 behavior 分布修复前 SCALP=31/SWING=77/POSITION=17/CHASE=0/FOMO=0 → 修复后 SWING=55/CHASE=23/SCALP=17/POSITION=16/FOMO=12，CHASE 与独立三条件复算完全一致。

#### 2. BUG-3：insight/whatif 慢路径不写快照（性能）

**现象**：`get_insight`/`get_whatif` 慢路径成功计算后直接 return，不写回 `insight_snapshot`/`whatif_snapshot`，而 `get_stats` 慢路径有 self-heal 写回。导致：① 每次请求都走慢路径（慢）；② 若 `run_analysis` 的 `compute_all` 失败（mootdx TCP 错误），insight/whatif 永久 null。

**修复**：`get_insight`/`get_whatif` 慢路径在 return 前写回快照并 commit，仿 `get_stats` 的 self-heal 模式（含 try/except rollback 防御）。

### 验证

- 独立复算脚本（`.tmp/audit/`，不 import 项目任何模块）：三方对比确认 BUG-1/3 属实、BUG-2/4/5/6 不属实
- 后端全套测试：**422 passed / 0 failed**（新增 8 个测试：BUG-1 6 个 + BUG-3 2 个，TDD 红绿循环）
- BUG-1 修复未破坏 drift 防护网（`test_compute_equivalence.py` 38 passed）与下游 insight/whatif/report/AI 测试

### 涉及文件

- 后端：`backend/app/engine/pattern.py`（SCALP/SWING/POSITION conf 1.0→0.5）、`backend/app/api/analysis.py`（get_insight/get_whatif 慢路径写回快照）
- 测试：`backend/tests/test_engine/test_pattern.py`（+6 测试 + 更新 3 个旧 confidence 断言）、`backend/tests/test_engine/test_compute_equivalence.py`（+2 测试）

### 审计误判教训

审计员手工复算的 3 处错误值得记录，避免后续审计重蹈：
1. **漏扣 commission**：手工 sim_pnl 不扣双边费用但 orig_pnl 含费用，导致 BUG-4/5 delta 偏正。FINANCE_DOMAIN.md §1 明确要求扣双边费。
2. **漏解析 resolve_per_category**：手工只数 `tag_market_patterns` 产出，不模拟 behavior 维度互斥，导致 BUG-1 数值与系统不可比。
3. **误解 HOLD_LOSER/CUT_WINNER 定义**：FINANCE_DOMAIN.md "持仓中位数"表述可整体可逐仓，审计员按整体判断，与代码逐仓位实现不符（代码实现合理）。

---

## [V1.2.3] — 2026-06-30

### 概述

V1.2.2 修复了 AI 报告反事实方向 bug，但 WhatIf 引擎只有"固定止损"一种反事实，等于只问"少亏多少"，不问"少赚多少"。散户典型病灶是"截断利润让亏损奔跑"——华西真实数据：小赚离场 17 笔胜率 100% 只赚 9352，大亏离场 5 笔亏 36091，盈亏失衡根子在止盈过早。本版本新增移动止损/固定止盈/移动止盈三种反事实规则，补齐止盈侧诊断；同时修正现有固定止损的参数档位（5%→8% 标准档）和 T+1 bug（bar 遍历从 entry_date 当日起，违反 A 股当日不可卖）。

### 新增功能

#### 1. 三种反事实规则（引擎层 `whatif.py`）

`analyze_rule` 新增 3 个 `rule_type` 分支，与现有 `stop_loss` / `stop_loss_large_loss` 平级：

- **移动止损 `trailing_stop`**（trail 8%）：跟踪持仓期间最高价(high)，止损价随最高价上移（只上不下），回撤 8% 触发卖出。过滤洗盘、锁定浮盈。涨停板不触发顺延，停牌跳过保持前值。
- **固定止盈 `take_profit`**（+10%）：涨到 +10% 触发卖出。截断利润方向的反事实——回答"机械止盈会多赚还是少赚"。
- **移动止盈 `trailing_take_profit`**（模式 A：5%/5%）：盈利达 5% 才激活移动止损保护，未激活前不干预；激活后 `stop_price = max(max_high×(1-trail_pct), entry_price)` 确保不亏出。让利润奔跑 + 保护利润。

三规则复用 `RuleSimulationItem` schema（`rule/original_return/what_if_return/delta/affected_positions`），`delta = 模拟后收益率 − 现状值`，`delta > 0` = 规则改善（统一语义）。

#### 2. AI 报告新增 `scenario_backtest` 段（独立成段）

- **采集**（`report.py`）：`generate_report` 补 5 个 `analyze_rule` 调用（含现有 2 + 新增 3），`_build_analysis_data` 新增 `scenario_results` 参数 + `scenario_backtest` key
- **渲染**（`prompt.py`）：新增"情景回测（规则模拟）"段，5 行口径说明 + 逐项渲染（规则名/触发次数/delta/模拟后收益率）；与现有 whatif 段**分开**（delta 语义主体不同：应用规则 vs 移除行为，合并会让 AI 混淆——V1.2.0/V1.2.2 方向 bug 教训）
- **校验**（`validator.py`）：对每项 delta 软校验（±1% 容忍，仿 PF 范式），不匹配记 warning 不阻断
- **SYSTEM_PROMPT** 数据真实性规范补第 8 条：回测数字是反事实模拟，禁用"保证收益/实际能赚/能让你/帮你"因果暗示词
- **契约**（`AI_INPUT_CONTRACT.md`）：`stop_loss` 从第 4 层"不喂"移出，第 3 层新增 `scenario_backtest` 行

#### 3. 前端情景回测 tab 新增展示（`WhatIfTab.tsx`）

- **策略对比速览矩阵**（顶部首屏）：6 行表格（现状/固定8%止损/大亏止损/移动止损8%/固定止盈10%/移动止盈5%/5%），列含模拟后收益率/变化(delta)/触发/评级，delta 颜色正绿负红，口径说明行。用户一眼看出哪个规则对自己最有效
- **3 张新卡片**（SECTION 1b 后）：📈 移动止损 / 🎯 固定止盈 / 🚀 移动止盈，复用大亏止损卡片骨架，三档文案（改善/拉低/中性）遵守描述性原则
- 现有止损卡片文案 5%→8%

### 修复的 Bug

#### 4. 固定止损 5% → 8%（标准档对齐）

**问题**：现有固定止损默认 5% 是保守偏紧档（A 股散户标准是 8%）。项目自有数据为铁证——V1.2.2 记录"5% 线太紧，59 次触发但净效果≈0"。5% 在 ±10% 涨停板下处于"半个涨停板"位置，正常波动即触发。

**修复**：`analysis.py:get_whatif` 的 `stop_loss` 和 `stop_loss_large_loss` 的 `loss_pct` 0.05 → 0.08。三处阈值自洽：固定止损 8% = 移动止损 trail 8% = 大亏止损阈值 `pnl_pct < −8%`。

**历史基准归档**：V1.2.2 的"整体 5% 止损 delta=−0.02%"是 5% 档历史基准，改默认值后不可直接比较。8% 档华西实测 delta=+0.22%（向正方向变大，因误杀减少），符合预期。

#### 5. T+1 修正（入场当日不可卖）

**问题**：`stop_loss` 和 `stop_loss_large_loss` 的 bar 遍历条件 `p.entry_date <= bar_date` 包含入场当日，但 A 股 T+1 当日买入不可卖，入场当日触发止损不现实。

**修复**：两处 `<=` → `<`（`whatif.py:174, 247`），3 个新规则从一开始就用 `entry_date < bar_date`。

### 验证

- 后端引擎：华西三份交割单离线复算 5 规则 delta：固定8%止损 +0.22% / 大亏止损 +2.35% / 移动止损8% −0.59% / 固定止盈10% +1.33% / 移动止盈5%/5% −0.45%
- 移动止损/移动止盈 delta 为负是**真实反事实信号**（非 bug）：华西持仓日内振幅中位 4.5%、>8% 占比 14%，8%/5% 阈值偏紧，移动止损 74 次触发中 62 次（84%）误杀。这是参数选择问题，引擎逻辑正确
- AI 采集 + 渲染：`scenario_backtest` 5 项全采集，prompt 段正确渲染，口径说明成对出现
- 前端 TypeScript：0 错误
- 后端 import + schema：5 个 `Optional[RuleSimulationItem]` 字段就绪，openapi 确认 3 新规则已加载
- uvicorn 重启加载新代码（按 PROJECT_EXPERIENCE「僵尸 worker 陷阱」树形杀进程）

### 涉及文件

- 后端：`backend/app/engine/whatif.py`（T+1 修正 + 3 新规则）、`backend/app/schemas/analysis.py`（+3 字段）、`backend/app/api/analysis.py`（改 8% + 调 3 新规则）、`backend/app/api/report.py`（补 analyze_rule + scenario_backtest 采集）、`backend/app/ai/prompt.py`（scenario_backtest 段 + SYSTEM_PROMPT 规范）、`backend/app/ai/validator.py`（scenario 软校验）
- 文档：`docs/superpowers/AI_INPUT_CONTRACT.md`（移出 stop_loss + 新增 scenario_backtest）
- 前端：`frontend/src/pages/tabs/WhatIfTab.tsx`（速览矩阵 + 3 新卡片 + 8% 文案）

---

## [V1.2.2] — 2026-06-30

### 概述

本版本是 V1.2.0「AI 报告反事实方向 bug」修复的**展示层收尾**。V1.2.0 修了 `prompt.py` 的 AI 层方向错误（PYRAMID/TURN 被说成拖累），但前端归因展示层仍是同一根因的另一种表现——用描述性字段 `absolute_impact` 分组却用反事实文案「赚钱靠什么」，与真反事实 `delta` 方向 11/12 相反。经华西三份交割单（224 笔成交 / 94 有效持仓）真实数据复算逐项核对后，重构 WhatIf/Insight 两个 tab 的归因语义，并新增「大亏止损模拟」补齐 outcome 维度的反事实缺口。

### 修复的 Bug（展示语义）

#### 1. 情景回测「赚钱靠这些/亏钱因为」方向说反（高危，与 V1.2.0 同源）

**现象**：WhatIfTab 用 `absolute_impact`（描述性累计 PnL）分组，文案「赚钱靠什么」却暗示因果。华西数据 12 个标签中 11 个 `absolute_impact` 与真反事实 `delta` 方向相反——波段(SWING)被放「赚钱靠这些」(净赚 +1,212)，但真反事实显示移除后收益率从 −2.45% 暴跌到 −6.28%（波段是救命稻草，不是赚了 1,212）。

**根因**：`absolute_impact = total_pnl − filtered_pnl`，数学上等价于该标签持仓净 PnL 之和（与 InsightTab 的 `total_pnl` 完全等价，12 标签 diff 全 = 0.00）。两个 tab 在算同一件事却展示成不同结论。真正的反事实是 `delta = what_if_return − original_return`。

**修复**（方案 A）：WhatIfTab「盈亏来源速览」重构为「少做哪些能改善收益」——
- 分组字段 `absolute_impact` → `delta`：`delta>0`（移除后收益率↑）=「⚠️ 少做这些能改善收益」；`delta<0`（移除后收益率↓）=「💪 这些在帮你扛收益，别乱砍」
- 维度过滤：只归因 behavior + psychology，剔除 market_env（环境不可选）和 outcome（事后分类，对它们做"移除"无意义）
- 显示 `delta`（收益率变化）取代 `absolute_impact`（绝对金额）；删除「贡献了总收益的 X%」文案（`contribution_pct` 是对 `abs(delta)` 的归一化，非"占总收益比"，在亏损账户上会显示荒谬的"贡献 100%"）

#### 2. 「大亏离场」看不到 whatif（设计缺口，方案 B 彻底修复）

**现象**：LARGE_LOSS_EXIT 是 outcome 结果标签，对它做"移除后重算"是同义反复（"亏钱因为大亏离场"等于没说）。用户真正想问的是「如果给这些大亏笔设了止损会怎样」，但引擎只有"整体止损"一种反事实。

**修复**（方案 B，后端新增规则）：`whatif.py:analyze_rule` 增加 `stop_loss_large_loss` 规则类型——仅对 `pnl_pct < −8%`（与 LARGE_LOSS_EXIT 阈值一致）的大亏持仓做 5% 止损模拟，其余持仓保持原 PnL。
- `WhatIfResponse` 新增 `stop_loss_large_loss: Optional[RuleSimulationItem]` 字段（schema 向后兼容，旧快照反序列化为 None）
- 前端新增「🩹 大亏止损模拟」区块，与「💡 止损效果模拟」形成对照
- 华西实测：整体 5% 止损 delta=−0.02%（59 次触发，挽回与误杀抵消，5% 线太紧）；仅大亏止损 delta=**+3.0%**（14 笔触发，收益率从 −2.45% → +0.59%，翻盘为正）——大亏是亏损主因，止损能切实挽回

#### 3. 诊断结论「勉强打平」误导

**现象**：`baseline_expectancy = +0.29%`（R-multiple 口径）落前端 else 分支，显示「期望接近零，扣除手续费后勉强打平」。但真实情况 PF=0.56、总亏 −3.5 万、连续亏 11 次，明显亏钱。

**根因**：R-multiple 期望与金额口径在胜率≈50% 时冲突——胜率 52% 略高于 50% 让 R 期望翻正，但亏损笔金额更大，金额口径下严重亏损。

**修复**：conclusion 在 baseline≈0 分支叠加净额判断——`netPnl<0` 时说「虽然按收益率算期望接近零，但亏损笔金额大于盈利笔，整体仍在亏钱」。

#### 4. 最大回撤「+5.63万」误导 + 与大亏离场脱节

**现象**：① 回撤金额显示 `+5.63万`，正号误导成盈利；② 4% 的回撤率太抽象，用户无法和「大亏离场亏 5.9 万」联系起来。

**根因**：`formatMoney`（`utils/format.ts`）为盈亏设计（`value>0 → "+"`），但回撤金额是正数表示亏损量，套用被加误导性 +。

**修复**：StatsCards 加局部 `fmtDrawdown`（无符号万级格式）；「最大回撤」card 副标题补回撤金额 + 单笔最深亏损 + 占比——「回撤 5.63万（4.0%），单笔最深 -1.05万，占回撤仅 19%，其余来自多笔累积——需整体减少亏损频次」。关联了「单笔不是主因、是 14 笔累积」的真实结构。

#### 5. 柱状图不过滤样本不足

**现象**：`PatternChart` 把 BEAR_TREND(2笔)/BREAKOUT(3笔)/TIME_EXIT(1笔) 等小样本也画进胜率柱状图，无统计意义。

**修复**：过滤 `count<5`，全空时显示「样本不足，暂无可绘制的行为标签」。

#### 6. 市场环境标签评价「建议减少」不当

**现象**：BULL_TREND 评价显示「负期望：持续亏损，建议减少或改进」——但环境不可选，不能"减少牛市交易"。

**修复**：InsightTable 评价逻辑加 market_env 分支——环境标签不给行动指令，改为描述性「在此环境下反而亏损（胜率仅 48%），可能追高被套」/「在此环境下整体盈利」。

#### 7. 命名统一 + 止损区块缺解释 + InsightTab 撞名

- **ShapleyPanel** 折叠标题「赚钱来源分析（公平归因）」→「Shapley 归因（各标签对总收益的公平贡献）」，与 WhatIfTab「Shapley 归因 + 因子贡献详情」统一
- **WhatIfTab 止损** delta≈0 的 else 分支补解释「盘中触发 59 次，止损挽回的大亏与误杀的盈利基本抵消」
- **InsightTab** 标题「赚钱靠这些/亏钱因为这些」→「赚钱的行为/亏钱的行为」，与 WhatIfTab 反事实语义分离；count<5 加「样本不足」标记
- **WhatIfTab 因子贡献详情**（折叠区）按 behavior+psychology 过滤，补说明「市场环境不可选、交易结果是事后分类，对它们做移除无意义，大亏的对策请看上方大亏止损模拟」

### 验证

- 后端引擎：华西三份交割单离线复算，`stop_loss_large_loss` 返回 delta=+3.06% / 14 笔触发（与整体止损 delta=−0.02% 形成对照）
- 前端 TypeScript：0 错误
- 后端 import + schema：`WhatIfResponse.stop_loss_large_loss` 字段就绪，`RuleSimulationItem` 字段完整
- uvicorn 重启加载新代码（按 PROJECT_EXPERIENCE「uvicorn --reload 僵尸 worker 陷阱」记录，`taskkill //F //T //PID` 树形杀 reloader+worker，openapi 确认新字段已加载）
- 真实数据核对：最大回撤 5.63万（3.89%）/ 单笔最深 -1.05万占 19% / 14 笔大亏合计 -5.9万

### 涉及文件

- 后端：`backend/app/engine/whatif.py`（新增 `stop_loss_large_loss` 规则）、`backend/app/api/analysis.py`（调用新规则）、`backend/app/schemas/analysis.py`（新增字段）
- 前端：`frontend/src/pages/tabs/WhatIfTab.tsx`（方案 A 重写 + 大亏止损区块）、`frontend/src/pages/tabs/InsightTab.tsx`（文案+conclusion+样本标记）、`frontend/src/components/StatsCards.tsx`（回撤文案+formatMoney +号修复）、`frontend/src/components/InsightTable.tsx`（市场环境评价）、`frontend/src/components/PatternChart.tsx`（样本过滤）、`frontend/src/components/ShapleyPanel.tsx`（命名统一）

---

## [V1.2.1] — 2026-06-30

### 概述

本版本是 `V1.1_IMPROVEMENT_PLAN.md` 前端审查报告中 **P1 + P2 优先级任务**的实施收尾，延续 V1.1.3 的前端 UX 打磨。P1（7 个 EPIC：A2 导航 / B3 KPI / C2 报告 / D2 昵称 / D3 管理员 / E1 响应式 / E2 A11y）分两批完成——第一批 5 个纯前端、第二批 D2/D3 涉及后端；P2 按决策收敛为 B5.1 归因进度条 + F1 组件复用 + F2 测试基础设施。所有改动经 Playwright E2E 回归套件（16 项）+ vitest 单元测试（19 项）验证通过。

### 新增功能（P1 第一批，纯前端 5 EPIC）

#### 1. 导航增强（A2）
- 顶部加「历史」直接链接（登录态），不再需点开头像 dropdown
- 当前页 active 高亮（桌面 + 移动，`/upload`/`/history` 变 accent）
- 移动端汉堡菜单展开时图标变色（视觉反馈）
- 新增 `BackToTop` 组件：滚动 > 600px 时浮动按钮出现，平滑回顶

#### 2. 核心 KPI 卡片规范化（B3）
- 抽公共 `utils/format.ts:formatMoney`：统一「元」单位 + 千分位 + 2 位小数，≥1万 附「万」简写与完整元；替换 StatsCards / SymbolSummaryTable / EquityCurve 三处重复的本地实现
- 胜率卡片显示分子分母：「22 笔赚钱 / 29 笔已平仓」
- 「完整交易 42 笔」改三档：「已平仓 29 笔」+ summary「总成交 N｜完整建仓 M｜已平仓 K（X 赚/Y 亏）」——修正 22+7≠42 的困惑（total_positions 含未平仓）
- hero 栅格断点 md→lg，中屏 2 列不再挤

#### 3. AI 报告可读性（C2）
- 章节目录：从 markdown 提取 `##`/`###` 标题渲染锚点 nav，点击平滑滚动（修复：AI 报告用 `###` 作章节，原 TOC 只提 `##` 不渲染）
- 「复制全文」按钮：一次复制整篇 Markdown 到剪贴板
- 按钮权重对调：「返回分析面板」变 primary（上下文切换），「下载/复制」为 outline
- h2/h3 带编码 id + `scroll-mt-20`（粘性导航偏移）

#### 4. 响应式（E1）
- Analysis 顶部按钮移动端缩小 + flex-wrap，不再换行溢出
- Landing Hero 字号分档 `text-3xl sm:text-4xl md:text-5xl`（移动端不超 36px）
- Feature 卡片间距 `mt-20`→`mt-10 sm:mt-16`，首屏可见 Trust 卡片
- 表格移动端卡片视图（B2.3 已做）、图表 ResponsiveContainer 已就绪——按决策不做通用 HOC

#### 5. 可访问性 A11y（E2）
- 跳过链接「跳到主内容」（sr-only + focus 可见，键盘第一焦点）
- 表单 input 加 `aria-label`/`aria-invalid`/`aria-describedby` 关联错误块
- 错误提示块 `role="alert"`，屏幕阅读器即时播报

### 新增功能（P1 第二批，D2/D3 后端）

#### 6. 注册可选昵称（D2）
- `RegisterRequest` 加可选 `nickname` 字段（2-20 字符），传了就用、没传走 `generate_nickname()`
- 前端 `RegisterForm` 加可选昵称输入框

#### 7. 管理员安全加固（D3）
- **路由不可猜**：`/admin` → `/admin-7c2b9e`，防自动化扫描
- **爆破锁定**：内存计数器，5 次失败/15 分钟 → 429「登录失败次数过多」；limiter 调到 20/min 让 per-username 锁定先触发（原 5/min 与锁定阈值相同，limiter 抢先掩盖）
- **登录审计**：User 加 `last_login_at`/`last_login_ip` + 迁移；登录成功记录时间+IP，返回上次登录信息；后台首页显示「上次登录」

### 新增功能（P2，按决策收敛）

#### 8. 归因分析贡献进度条（B5.1）
- `InsightTable` 新增「贡献」列：横向进度条宽度 = `|total_pnl| / sum(|total_pnl|)`，绿正红负，附百分比。B5.2 维度切换器跳过（InsightTab 已按 4 维展示）

#### 9. 组件复用（F1）
- 抽取 `KpiCard` 组件（variant hero/detail），统一 StatsCards 的 heroCard/detailCard 两个近似函数；`Rating`+`COLOR_CLASS` 内聚到 KpiCard
- F1.3 三态组件（EmptyState/LoadingSpinner/ErrorBox）已存在于 ui.tsx，无需做

#### 10. 测试基础设施（F2）
- **vitest 单元测试（19 项全过）**：配 vitest.config.ts + jsdom + setup（matchMedia/ResizeObserver polyfill）；format（8）、SymbolSummaryTable（7，搜索/排序/清空）、KpiCard（4）
- **Playwright E2E 回归套件（16 项全过）**：`frontend/tests/e2e/regression.py`，本地目标 + 每次新账号 + 断言式 check() + 非零退出码。覆盖注册→登录→上传→分析(三档/中文名/搜索/X)→Tab切换→归因进度条→AI报告(TOC/复制)→历史active→404→console 0 error

### 按决策不做

| EPIC | 决策 | 理由 |
|---|---|---|
| B4 WhatIf slider | 不做 | 保持固定 5% 止损 |
| C3 报告分享链接 | 不做 | 已有「复制全文」够用 |
| E3 暗色模式 | 不做 | 项目默认暗色，做「跟随系统」需定义全套明色 token，工作量过大 |

### 验证
- vitest 单元测试：**19/19 通过**
- Playwright E2E 回归：**16/16 通过**
- 前端 TypeScript：0 错误
- 后端 auth + admin 测试：28/28 通过

---

## [V1.2.0] — 2026-06-29

### 概述

本版本聚焦 **AI 诊断报告的质量与准确性**。起因：用户上传中信 2025 全年交割单后，发现报告存在"反事实回测方向说反""标签漏报""指标算未喂"三类系统性缺陷。经真实数据离线复算（211 笔成交 → 87 有效持仓）逐项核对后，修复 prompt 表述、补齐输入字段，并建立《AI 输入字段契约》从制度上根治"采集/渲染脱节"。

### 修复的 Bug

#### 1. 反事实回测方向说反（高危）

**现象**：报告称"移除金字塔加仓（PYRAMID）和逆势交易（TURN），收益会分别增加 -0.0391 和 -0.0252（即收益会更高），这些行为在拖累整体表现"。

**根因**：`prompt.py` 喂给 AI 的 `收益变化 {delta:+.4f}` 对 LLM 太暧昧——delta 为负实为"移除后少赚=利润来源"，AI 却读成"收益增加 -0.0391"，动词与负数打架后顺势推了相反结论。真实复算证实 PYRAMID(-0.0375)/TURN(-0.0235) 均为负 delta，是**利润来源**而非拖累；真正的拖累是 AVERAGE_DOWN(+0.0159, -7187元) 和 POSITION(+0.0165)，报告完全没提。

**修复**：whatif 段补判读口径说明——"delta 为负=在帮你赚钱（利润来源），delta 为正=在亏钱（拖累），不可把负数说成收益增加"。

#### 2. 优势/风险清单漏报高效标签

**现象**：报告优势清单只列了 SWING/SIDEWAYS/TRAILING_STOP（按总盈亏绝对额排序），漏掉了单笔均收益最高的 OVERTRADING（+13.08%）和 PSY_FOMO（32笔/+11793）。

**根因**：①SYSTEM_PROMPT 硬限"优势/风险各 2-3 个"，按绝对额排序挤掉小额高效标签；②只引导看总额不看效率；③patterns 只传 count/win_rate/total_pnl，**漏传 avg_pnl_pct**，AI 想看效率也没数据。

**修复**：优势/风险放宽为"覆盖各维度代表性标签，优先单笔效率最高者"；核心原则新增 #6 效率优先、#7 区分确定结论与低置信度推测（PSY_ 前缀须标"推测，置信度低"）；`_build_analysis_data` patterns 补 `avg_pnl_pct`，prompt 渲染"单笔均收益"。

#### 3. 指标采集了却没渲染（漏渲染 bug）

**现象**：`win_loss_ratio`（损益比）、`pnl_distribution`（盈亏量级分布）进了 `analysis_data`，但 `build_user_prompt` 没有对应渲染分支——数据算了等于白算。

**修复**：补渲染。损益比挂在盈亏比后，量级分布挂风险指标段末。

### 新增功能

#### 1. AI 输入字段契约（`docs/superpowers/AI_INPUT_CONTRACT.md`）

根治"哪些指标喂给 AI"长期无文档、按需零散加出导致的系统性缺陷。含 5 条筛选原则（采集=渲染一致 / 聚合优先 / 护栏字段必传 / 维度覆盖 / 系统算好的优先）、4 层字段清单（基础KPI / 风险指标 / 行为与归因 / 不喂及理由）、维护规则（新增字段三同步）。`CLAUDE.md` 加为第四份必读文档。

#### 2. 喂给 AI 的指标扩充（稳健档）

按契约补 5 项此前未喂的高诊断价值字段：
- `is_small_sample`：护栏，<5 笔提示"样本不足不评价"（落实 FINANCE_DOMAIN §四规范）
- `baseline_expectancy`：评价各行为盈亏的基准线
- `avg_win_holding_days` / `avg_loss_holding_days`：盈亏持仓天数对比，诊断"死扛"
- `shapley`：招牌功能"赚钱来源分析"（Shapley 归因），各行为对总盈亏的公平贡献
- patterns `dimension`：每标签后缀维度归属，防 AI 漏看某维度

### 验证

- 真实数据离线复算：PYRAMID(-0.0375)/TURN(-0.0235)/TIGHT_STOP(+0.0029) 与报告引用值逐项吻合，方向经代码口径证伪后纠正
- `tests/test_ai/` + `tests/test_api/test_report.py`：44 passed，无回归

---


## [V1.1.3] — 2026-06-29

### 概述

本版本是对 `V1.1_IMPROVEMENT_PLAN.md`（前端审查报告）中 **P0 优先级任务**的实施，外加实施过程中发现并修复的 3 个回归/缺陷、1 个 dev 环境陷阱、1 项结构重构。源自一次 Playwright 端到端全流程审查（注册→登录→上传 3 种券商 .xls→分析→报告→历史→管理员→移动端），审查产物归档于 `docs/review/frontend/`。

### 新增功能（P0，4 个 EPIC）

#### 1. 路由补齐与登录回跳（A1）

- `/analysis`、`/report` 无 id 时重定向到 `/history`（之前直接 404）
- `ProtectedRoute` 把当前 URL 作为 `?redirect=` 传给登录页，登录后回跳原页（防 open redirect：仅允许 `/` 开头且非 `//` 的内部路径）
- 404 页增加「热门目的地」入口（首页/上传/历史/登录），登录态隐藏登录入口

#### 2. 黄色警告 banner 整改（B1）

- 「N 笔持仓起始于交割单外」警告改为**可折叠徽章**，默认收起、点击展开，不再占用整屏视觉重心
- 文案中性化：「如需更准确结果，可补传更早期的交割单」（去掉「建议导入更早期以获得完整分析」的归咎语气）
- 展开后内嵌「一键添加更早的交割单」按钮 → 打开 `AddFileModal`（与顶部「+ 添加交割单」同路径，不跳转 `/upload`）

#### 3. 股票维度盈亏表升级（B2）

- **股票中文名**：`Trade` 表新增 `symbol_name` 字段 + alembic 迁移；SmartParser 识别 `证券名称`/`股票名称` 列（CJK 字符启发式 + 排除代码列/方向列）；`compute_stats` 与 `get_stats` 慢路径聚合时构建 `symbol → name` 映射。华西/中信/天风三券商 100% 命中。
- **移动端卡片视图**（≤768px）：每只股票一张卡，不再横向溢出
- **搜索框 + X 清空按钮**：按代码或名称即时过滤，一键清空恢复完整列表

#### 4. 注册/登录一致性与安全（D1）

- 注册/登录 placeholder 统一：「邮箱」/「11位手机号」/「密码（至少8位）」
- 登录页增加「邮箱登录 | 手机号登录」tab，与注册页对称
- 邮箱正则严格化：`/^[^\s@]+@[^\s@]+\.[^\s@]+$/`（拒绝 `a@.com` 等畸形值，两表一致）
- 防账号枚举：登录错误文案统一为「账号或密码错误」，不区分「账号不存在」与「密码错误」

### 修复的 Bug

#### 1. 添加交割单后股票名称全部消失（V1.1.3 引入的回归）

**现象**：通过「+ 添加交割单」上传第二份文件后，股票维度盈亏表所有股票名称消失，刷新页面也无效。

**根因**：`compute.py`（run_analysis 路径）和 `analysis.py`（get_stats 慢路径）**两处各自独立构建 symbol_summary**。P0 只在 `compute.py` 加了 `symbol_name_map`，`link_files_to_analysis` 清空 snapshot 后，下次 GET 走慢路径重算漏了 `symbol_name`，无 name 的 snapshot 覆盖了好的。

**修复**：`get_stats` 慢路径补 `symbol_name_map` 构建。验证：添加文件2 → 18/18 symbols 保留 name（之前 0/18）。

#### 2. AddFileModal 上传后 filenames 不刷新

**现象**：上传文件2 后，header 仍只显示「文件1」，需手动刷新页面才出现「文件1 + 文件2」。

**根因**：`onSuccess` 仅 `invalidateQueries`，但 modal 立即关闭 + `useStats` 有 5 分钟 `staleTime`，background refetch 可能没及时更新 UI。

**修复**：`onSuccess` 改为先 `removeQueries` 再 `invalidateQueries`，强制下次渲染重新请求后端。

#### 3. restart.py 后端启动崩溃（slowapi ModuleNotFoundError）

**根因**：`restart.py` 调用裸 `uvicorn`，PATH 解析到系统级 Python（无 slowapi）而非项目 venv。

**修复**：显式指向 `backend/.venv/{Scripts,bin}/uvicorn`，强制使用项目解释器。

### 重构

#### dedupe symbol_name_map（R1，code review 发现）

`compute.py:225` 和 `analysis.py:307` 原有逐字相同的 5 行 `symbol_name_map` 构建逻辑——正是回归 #1 的根因。抽取为 `common.py:build_symbol_name_map(trades)` 公共函数，两处调用同一实现，杜绝再次漂移。

#### 移除死 prop（R2）

`StatsCards.analysisId` 是 banner 改用 `onAddFile` 后的遗留死代码（声明但从不读）。从 `StatsCards` 接口、`StatsTab` 透传、`Analysis.tsx` 调用点三处移除。

### 文档与沉淀

- **前端审查报告**归档于 `docs/review/frontend/`：Playwright 审查脚本 `audit.py`、22 张截图、`audit_report.json`、`V1.1_IMPROVEMENT_PLAN.md`（5 主题 / 12 EPIC / 47 任务）
- **PROJECT_EXPERIENCE.md** 新增「uvicorn --reload 僵尸 worker 陷阱」章节：记录调试绕圈 1 小时的根因（`taskkill //IM uvicorn.exe` 只杀 reloader 不杀 worker）、Windows 双进程模型、判定「代码 bug vs 环境假象」的排查清单

### 验证

- SmartParser：华西/中信/天风三券商 388/388 笔交易正确解析证券名称
- 后端测试：parsers + engine + auth **232/232 通过**
- 前端 TypeScript：0 错误
- Playwright 端到端：注册→登录→上传→分析→tab 切换→生成报告→历史全流程通过

### 未做（按用户决策）

- **C1 弹窗时序**（P0）：用户要求「保持现状，用户看报告前需做选择」，未改动 `Report.tsx` 的 consent 弹窗逻辑

---

## [V1.1.2] — 2026-06-28

### 概述

本版本源自一次**线上实例端到端数据准确性验证**：投资研究员上传真实华西证券交割单（GBK / 伪 `.xls` / `="..."` 外壳），逐项核对分析面板，发现 2 处必改缺陷 + 1 处口径设计问题。三者共同特征是——**只在"账户整体亏损"场景下才暴露**，单文件盈利分析无法触发，属典型的"测试数据分布 ≠ 生产数据分布"盲区（见 `PROJECT_EXPERIENCE.md`）。全量 415 passed / 0 failed。

### 修复的 Bug

#### 1. 最大回撤百分比超过 100%（金融上不成立）

**现象**：合并两份华西交割单后（86 笔完整交易，总盈亏 -8475.39），分析面板显示"最大回撤 147.5%"。净值从峰值约 +1.8万 跌穿零轴到 -8550，导致 `max_dd / peak > 100%`。

**根因**：`compute.py:349`（`compute_stats` 主路径，写 `stats_snapshot`）与 `analysis.py:453`（`get_stats` 慢路径）两处 `max_drawdown_pct = max_dd / peak`。当 `cum_pnl` 从正峰值跌穿零轴变为负数时，`dd = peak - (负值) > peak`，于是百分比 >100%。原 fallback 仅处理 `peak==0`（从头亏到尾）场景，未覆盖"peak>0 但 trough 跌穿零轴"。

> **副本教训**：研究员初轮只指认了 `analysis.py` 慢路径，漏报 `compute.py` 主路径。若只修 API 端点，`run_analysis` 仍写错误快照，`get_stats` 走快路径返回旧值——修复无效。两处必须同步改。

**修复**：分母改用峰值账户净值 `total_invested + peak`（本金 + 峰值浮盈）。该口径在 trough 跌穿零轴时仍 ≤100%（除非亏损超本金即爆仓，此时 >100% 反而合理），且**完全吞并原 fallback**——`peak==0` 时分母退化为 `total_invested`，与原行为一致，不破坏"全程亏损"回归。`max_drawdown` 绝对值字段保持不变（仍反映真实跌幅金额）。新增红测试 `test_max_drawdown_pct_capped_at_100_when_trough_crosses_zero`（红 150.16% → 绿 ≤100%）。

#### 2. 诊断结论把正贡献标签误判为"最大问题"

**现象**：归因分析 tab 顶部"诊断结论"显示"最大问题是「害怕错过(心理)」，贡献 +2893元"——但该标签 57.1% 胜率、Expectancy +4.0%、PF 2.04，明明是**盈利**标签，正贡献金额却被定性为"最大问题"。

**根因**：`compute.py:415`（`compute_insight`）与 `analysis.py:642`（`get_insight`）两处 `significant[0] / significant[-1]`，取的是**跨维度拼接后的首尾**而非贡献极值。`analyze_by_category` 只对单维度内排序，多维度 `extend` 后整体不再有序，于是 `PSY_FOMO`（+2893）恰好排在末尾被选为 `worst_pattern`。前端 `InsightTab.tsx` 仅渲染后端字段，无 bug。

**修复**：提取模块级纯函数 `_select_best_worst_patterns`，显式按 `total_pnl` 排序——`best` 取正贡献最大、`worst` 取最负。全正时 `worst` 降级为"正贡献最小者"，全负时 `best` 降级为"负贡献最小者"，仅 1 个显著标签时 `worst=None`。两处调用点共用，消除重复。新增 `test_select_best_worst.py` 5 个单元测试（正负混合 / 全正 / 全负 / 单标签 / count<5 过滤）。

### 口径修复

#### 3. Shapley 归因百分比符号取反

**现象**：What-If tab"赚钱来源分析"中，总收益为负时**正贡献标签显示负百分比**（震荡市 +3999.54 渲染为 -47.2%），**负贡献标签显示正百分比**（大亏离场 -5547.22 渲染为 +65.5%）。散户会误以为赚钱的模式在亏钱。

**根因**：`compute.py:545`（主路径）与 `analysis.py:775`（慢路径）两处 `pct_of_total = shapley_value / total_pnl * 100`。`shapley_value` 带符号（正贡献为正），但 `total_pnl` 为负时除法反转符号。Shapley 值本身计算正确，问题在百分比口径。

**修复**：分母改 `abs(total_pnl)`，使百分比符号跟随 `shapley_value`——正贡献恒显正%、负贡献恒显负%。带符号和 = ±100%（因 `sum(shapley) == total_pnl`），仍符合"总和=100%"的绝对占比语义。前端 `ShapleyPanel.tsx` 颜色本就按 `shapley_value` 判断（正确），无需改动。新增 `test_shapley_pct_sign.py` 3 个测试（负总收益下符号一致 / 正总收益下不破坏 / 带符号和=±100%）。

### 验证方式

线上实例（`http://47.109.159.232/`）上传华西 2025-10~12 + 2026-01~03 两份交割单复现全部三处问题，本地修复后回归确认。SmartParser 对真实券商格式（GBK 编码 / 伪 `.xls` TSV / `="..."` 外壳）解析稳健，核心 KPI（PF、Expectancy、净值曲线、止损回测）计算准确。

---

## [V1.1.1] — 2026-06-28

### 概述

本版本是 V1.1.0 的**代码审查收尾**：对 V1.1.0 提交做深度审查后，修复了 1 个发版阻断项、3 个合规/质量问题、2 个性能项，并根治了 1 个既有 flaky 测试。新增 5 个回归测试，全量 404 passed / 0 failed。审查过程覆盖金融定义口径、DB 事务边界、用户隐私合规、性能热路径。

### 修复的 Bug

#### 1. 存量脏快照永久 422（发版阻断项）

**现象**：V1.1.0 修复了"新写入快照完整"的问题，但**部署前已存在的 12 字段不完整快照**（truthy dict）无任何处理——快路径 `if analysis.stats_snapshot:` 为真 → `StatsResponse(**不完整dict)` 缺必填字段 → ValidationError → 422 永久卡死，存量分析无自然恢复路径。

**根因**：`get_stats` 快路径只处理 `None`（跳过），不处理"truthy 但不完整"的存量脏快照。

**修复**：快路径加 `try/except`，捕获 `ValidationError` 后置 `stats_snapshot=None` → fall through 到慢路径 → 慢路径重算并写回完整快照，**自愈**存量分析。新增红测试 `test_stale_partial_snapshot_self_heals`（TDD：旧实现 `4 validation errors` → 修复后 200）。

#### 2. clear_trades 删除 consent_log 审计记录

**现象**：`clear_trades`（清空用户数据）物理删除 `ConsentLog` 行，但 `consent_log` 是"immutable compliance audit trail"（不可变合规审计留痕）。

**根因**：用户同意贡献案例后，案例数据已复制进 `case_library` 表独立留存；用户清空的是自己账户的原始交割单/分析，**不应也不需**删掉已贡献案例的副本。但 consent_log 被一并删除，导致"案例在库、同意证据没了"的不一致——同意证据销毁，无法事后举证授权。

**修复**：`clear_trades` 不再删除 `ConsentLog`，保留全部同意/拒绝记录作为合规证据（与用户讨论确认方案 A）。新增红测试 `test_clear_trades_preserves_consent_log`（旧实现 `0 = len([])` 删光 → 修复后保留 2 条）。`ConsentLog.user_id` 的 `ondelete=CASCADE` 暂不动（当前无账户注销，不会触发）。

#### 3. report 与 /insight 端点的行情竞态 flaky（根治）

**现象**：`test_report_insight_matches_insight_endpoint` 是既有 flaky 测试，连跑原代码 8 次中 4 pass / 4 fail（50%）。

**根因**：report 端点每次用**当前行情** `compute_insight` 重算 `insight_items`，而 `/insight` 端点命中快路径读 `run_analysis` 时生成的 `insight_snapshot`（历史行情）。mootdx 行情抖动时两端 market_env 标签（SIDEWAYS 等）偶发不一致 → patterns 集合差异 → 断言 flake。

**修复**：report 的 `insight_items` 优先读 `analysis.insight_snapshot`（与 `/insight` 端点**同源**），无快照才回退 `compute_insight`（legacy 分析）。从源头消除重算竞态，附带省掉一次 PatternEngine 打标。连跑 10 次全绿，flaky 根治。新增 `test_report_recomputes_insight_when_no_snapshot` 锁定回退分支。

### 性能优化

#### 4. report.py 复用打标结果（PatternEngine 成本减半）

**根因**：report.py 打标一次供 WhatIf 的 `patterns_map`，`_build_category_map` 内部又完整重算一次 `tag_position`/`tag_market_patterns`/心理学检测，PatternEngine 成本翻倍。

**修复**：`_build_category_map` 新增 `precomputed` 参数，传入已打标的 PatternResult 列表时跳过重复打标，只跑 `resolve_per_category`。report.py 打标一次复用。新增 `test_build_category_map.py` 锁定 precomputed 路径与非 precomputed 路径输出**恒等**（相同输入下，防止 report 与 /insight 数据源漂移）。

#### 5. run_analysis 省 redundant SELECT

`run_analysis` 的 `except` 块 `db.rollback()` 后，return 处改用预捕获的 `aid` 替代 `analysis.id`，省一次 refresh SELECT（rollback 后访问 `analysis.id` 会触发额外查询）。

### 测试加固

- drift 等价性测试补 `LARGE_CSV` 大样本夹具（5 position / 全 SWING / 3 盈 2 亏），让 `best_pattern`（count≥5）与 `stop_loss`（亏损持仓 pnl_pct<-5%）非空，Insight/WhatIf 等价性断言不再退化为 `None==None` 平凡通过。覆盖 V4.0 的 `equity_curve` 逐点值、`pnl_distribution`、MAE/MFE 字段。

## [V1.1.0] — 2026-06-27

### 概述

本版本是一次**深度代码审查与质量加固**，起因是用户报告的「生成 AI 报告后返回分析面板数据丢失」故障。围绕该故障定位根因后，顺藤摸瓜展开全量审查，按用户操作路径（认证→上传→分析→查看→AI 报告→案例库→管理）补全了所有缺失测试，清理了死代码，并追查修复了 3 个此前潜伏的 bug。新增 63 个测试，全量 398 passed / 0 failed。

### 修复的 Bug

#### 1. 分析面板数据丢失（422 ValidationError）—— 本次审查的起点

**现象**：用户在服务器上上传交割单 → 看分析面板正常 → 生成 AI 报告 → 返回分析面板 → 页面报错看不到数据 → 点历史报告再进仍看不到。

**根因**：`get_stats` 端点的两个路径写入的快照不一致：
- 快路径 `StatsResponse(**analysis.stats_snapshot)` 要求 40 个字段（含必填 `positions`/`max_win`/`max_loss`/`consecutive_losses`）
- 慢路径（`analysis.py` 旧 line 449-463）只保存 **12 个字段**的 dict

当 `run_analysis` 的 `compute_all` 在服务器上因 mootdx TCP 异常失败时，快照保持 `None`；首次 `get_stats` 走慢路径返回完整数据（用户看到正常）**+ 用 12 字段不完整快照覆盖**；第二次走快路径 → `StatsResponse(**12字段)` 缺必填字段 → ValidationError → 422 → 前端显示"加载失败"，快照被永久污染。

**修复**：
- `get_stats` 慢路径改为存完整的 `response.model_dump()`（而非手写 12 字段 dict）
- `run_analysis` 的 `except` 块新增 `db.rollback()`（失败后 session 污染是 pre-existing 缺陷，导致后续查询全部 `PendingRollbackError`），且 `aid` 在 try 前捕获（避免在 poisoned session 上访问 `analysis.id` 再次崩溃）
- `link_files_to_analysis` 删除冗余的第二次清空+commit（双重清空无意义）
- `MarketDataCache.store_bars` 的 SQLite 路径原本假设所有 bars 同一 symbol（`symbol = bars[0]["symbol"]`），且不处理 within-batch 重复 → 多 symbol 场景漏存 + mootdx 分页重复触发 UNIQUE 冲突。改为按 `(symbol, date)` 元组去重，与 PostgreSQL 的 `ON CONFLICT DO NOTHING` 语义一致

#### 2. 追加交割单后 date 范围未更新

**根因**：`link_files_to_analysis` 在 `db.add(AnalysisFile(...))` 后调用 `get_raw_file_ids` 查询，但测试环境 `autoflush=False`，查不到未提交的新行 → `date_start/end` 不扩展到新文件的交易日期。

**修复**：查询前显式 `db.flush()`。被新测试 `test_link_files_adds_files_and_invalidates_snapshot` 抓出。

#### 3. 上传去重拒绝重传（409 Conflict）

**现象**：两个测试（`test_reimporting_same_statement_does_not_double_count`、`test_multiple_contributions_add_rows`）长期失败，经 stash 对比确认在干净 master 上也失败。

**根因**：`upload_file` 检测到相同 sha256 内容时返回 **409 拒绝**，而非幂等返回已有文件。用户误传同一交割单（改名重传）会被拒绝，无法继续。

**修复**：检测到重复 hash 时**幂等返回已有 RawFile 的 id**。`import_trades` 本身已做交易去重，`_load_trades` 按 `raw_file_id` 过滤，不会双倍计数。

#### 4. AI 报告与 Insight 面板数据源不一致

**根因**：`report.py` 用 `InsightEngine.analyze`（单主模式：每笔交易只归一个主模式，按 `total_pnl` 原始值排序，无样本量门槛），而 `/insight` 面板用 `analyze_by_category`（多桶：每笔交易归入所有匹配模式，按 `total_pnl * log(count)/log(5)` 加权排序，`best_pattern` 还要 `count>=5` 过滤）。

**用户可见影响**：AI 报告可能把 `count=1` 的高盈利模式列为"最佳"，而面板因 `count<5` 过滤掉它，显示另一个模式。

**修复**：`report.py` 改用 `compute_insight`（与面板/`compute_all` 同一数据源），AI 报告与 `/insight` 面板用完全相同的 insight 数据。删除未使用的 `InsightEngine` import。

### 测试补全（新增 63 个测试，6 个文件）

按用户操作路径补全所有零覆盖端点：

| 用户路径 | 测试文件 | 覆盖端点 | 测试数 |
|---|---|---|---|
| 认证 | `test_auth_extra.py` | logout / PUT /me / password-strength | 12 |
| 上传清理 | `test_upload_lifecycle.py` | DELETE /trades（FK-safe 删除） | 4 |
| 分析列表+追加 | `test_analysis_list_and_link.py` | GET /analysis / link-files | 8 |
| 报告查询下载 | `test_report_download.py` | check by-analysis / download .md | 7 |
| 管理 | `test_admin.py` | 全 7 个 admin 端点 | 23 |
| drift 防护 | `test_compute_equivalence.py` | 慢路径 == compute_all | 3 |
| 报告一致性 | `test_report.py`（追加） | report insight == /insight | 2 |
| 快照回归 | `test_analysis.py`（追加） | TestSnapshotRoundTrip | 4 |

**drift 防护网**（`test_compute_equivalence.py`）：清空快照 → GET /stats/insight/whatif（慢路径）→ 与 `compute_all` 直接计算结果比较。这是防止再次出现 422 那类 drift 的核心防护。

> 注：whatif 等价性测试初版用了错误 JSON key（`attribution`/`rule_simulation`，schema 实际是 `items`/`stop_loss`），导致断言恒为空通过——已修复为正确字段名 + 实际值比较。shapley 因蒙特卡洛采样（`random.shuffle` 无种子）有算法随机性，改为容差比较（5% 或 1.0 绝对值）。

### 代码清理（删除死代码）

| 死代码 | 位置 | 处理 |
|---|---|---|
| `pattern_config.py` 整模块（70 行） | `engine/pattern_config.py` | 删除（零引用 + 引用不存在的 `pattern_definition.yaml`，一旦触发 FileNotFoundError） |
| `PatternEngine.detect_cooldowns` | `pattern.py:368-407` | 删除 + 删除 3 个独占测试；不变量测试迁移到 `TestTagCoexistence` |
| `_get_multiplier` | `parsers/__init__.py` | 删除 + 删除独占测试（SmartParser 用自己的 `_get_futures_multiplier_smart`） |
| `BaseParser._column_match_score` | `parsers/base.py:157` | 删除 + 删除独占测试（SmartParser 用自己的 `_classify_column`） |

> `PositionBuilder.build_grouped`（~130 行）仅 golden_runner + 测试用，自身注释承认是"参考实现"——保留（golden_runner 依赖）。

### 记录但未改动的隐患（供未来审查参考）

以下隐患经调查确认，本次未改动（风险/范围考量），已用测试锁住或记录归档：

#### A. get_stats/get_insight/get_whatif 慢路径与 compute.py 重复（~280 行）

`analysis.py` 的三个 GET 慢路径是 `compute.py`（`compute_stats`/`compute_insight`/`compute_whatif`）的手工副本。`get_stats` 副本**已导致过 422 bug**（本次已修）。

- **现状**：当前副本与 engine 行为一致，由 `test_compute_equivalence.py` 锁住。
- **未重构原因**：`compute_all` 用并行 fetcher（`ensure_market_data_parallel` + ThreadPoolExecutor），慢路径用串行 `ensure_market_data`；上轮尝试用 `compute_all` 替换触发 `PendingRollbackError`（daily_bars 重复插入），并发模型变更风险较高。
- **建议**：未来若要消除重复，需先评估并行 fetcher 的 session 安全性，并在 GET 端点包裹 `try/except db.rollback()`（镜像 `run_analysis` 的模式）。

#### B. get_insight / get_whatif 慢路径不写快照

与 `get_stats`（写快照）和 `run_analysis`（写全部三个快照）不同，`get_insight`/`get_whatif` 的慢路径**不持久化快照** → 每次请求重复全量计算。这是性能问题，非正确性问题。

#### C. get_whatif 的 rule_type guard 是死代码

`get_whatif` 用 `if rule_type == "stop_loss":` guard 止损模拟（`analysis.py`），而 `compute_whatif` 无此 guard。但前端**从不传非默认值**，且即使传了，`analyze_rule` 也只处理 `stop_loss`。当前行为一致，guard 无害，保留以防前端未来扩展。

#### D. MAE/MFE 的 lookback 范围差异（理论性）

慢路径的 `ensure_market_data` 返回 120 天 lookback 扩展的 market_data，`compute_all` 的 `get_market_data` 用原始窗口。但 `compute_mae_mfe` 的 position 窗口过滤（`entry_date <= bar_date <= exit_date`）恰好掩盖了差异——当前不触发。若未来 position 的 `entry_date` 早于 `analysis.date_start`，两边会 diverge。

#### E. report.py 的内联 stats 计算（B2，未处理）

`report.py` 的 `_build_analysis_data` + `generate_report` 内联重算了 profit_factor/max_drawdown/consecutive_losses/MAE/MFE/expectancy 等（~200 行），与 `compute.py` 重复。本次仅统一了 insight 数据源（问题 4），stats 计算仍重复。建议未来复用 `compute_all` 的 stats 结果。

#### F. 三个近似的 raw-file 读取器

`upload.py:_read_raw_content`、`admin.py:_read_raw_file_bytes`、`case_library.py:_read_and_decode_raw_file` 三个读取器逻辑近似，建议未来合并到 `common.py`。

### 变更文件清单

```
修改:
  backend/app/api/analysis.py        # get_stats 完整快照 + run_analysis rollback + link_files flush
  backend/app/api/report.py          # analyze → compute_insight 统一数据源
  backend/app/api/upload.py          # 去重 409 → 幂等返回
  backend/app/engine/market_data.py  # store_bars (symbol,date) 去重
  backend/app/engine/pattern.py     # 删除 detect_cooldowns
  backend/app/parsers/__init__.py   # 删除 _get_multiplier
  backend/app/parsers/base.py       # 删除 _column_match_score
  backend/tests/test_api/test_analysis.py       # +TestSnapshotRoundTrip
  backend/tests/test_api/test_report.py         # +TestReportInsightConsistency
  backend/tests/test_api/test_upload.py         # 更新去重测试断言
  backend/tests/test_engine/test_pattern.py     # 迁移 detect_cooldowns 测试
  backend/tests/test_parsers/test_helpers.py    # 删除 _get_multiplier 测试
  backend/tests/test_parsers/test_registry.py  # 删除 _column_match_score 测试
删除:
  backend/app/engine/pattern_config.py
新增:
  backend/tests/test_api/test_auth_extra.py
  backend/tests/test_api/test_upload_lifecycle.py
  backend/tests/test_api/test_analysis_list_and_link.py
  backend/tests/test_api/test_report_download.py
  backend/tests/test_api/test_admin.py
  backend/tests/test_engine/test_compute_equivalence.py
```

---

## [V1.0.0] — 2026-06-26

### 首个正式版本

经过 6 个月的迭代开发（V0.1.1 → V0.5.0），TradeDoctor 达到 v1.0 里程碑。本版本具备完整的「交割单上传 → 持仓重建 → 行为标签 → 盈亏归因 → AI 诊断报告」分析链路，并提供匿名案例库贡献的数据闭环。

### 核心能力

- **SmartParser 自动解析**：基于数据值推断列类型，支持 6+ 券商格式，GBK 编码容错、伪 `.xls` 回退、`="..."` 外壳剥离
- **FIFO 持仓重建**：前序持仓 `cost_known` 标记，软删除 `is_deleted` 支持
- **4 维行为标签体系**：市场环境 / 交易行为 / 交易结果 / 心理推测，每持仓每维最多一个标签
- **Insight Engine**：PF、Expectancy(R)、Shapley 归因、Primary Pattern 识别
- **What-If 止损回测**：持仓期间日线 low 判断盘中触发，因子贡献分析
- **MAE/MFE 风险分析**：持仓期间最大浮亏/浮盈，止盈效率 `profit_capture_ratio`
- **AI 诊断报告**：自然语言报告，Prompt 携带 10+ 风险指标 + 关键交易摘要
- **净值曲线 + 股票盈亏表**：按持仓退出日累计，按个股汇总
- **匿名案例贡献**：用户主动同意的匿名交割单收集，consent_log 审计追踪确保合规

### V1.0 新增（自 V0.5.0 以来）

- **交割单去重**：SHA256 内容哈希 + 交易唯一键双重去重，防止重复导入
- **ConsentLog 合规审计**：用户同意/拒绝决策不可变记录，满足《个人信息保护法》合规证明需求
- **Landing 页内联认证**：注册/登录无需跳转页面
- **UI 全面优化**：设计令牌体系、焦点陷阱、ESC 关闭、Tailwind 迁移、性能优化
- **部署完善**：rsync 全量同步、server-setup.sh 首次安装、跨平台重启脚本

## [V0.4.0] — 2026-06-23

### 新增

- **净值曲线图**（Equity Curve）
  - 后端：`StatsResponse` 新增 `equity_curve: list[EquityPoint]` 字段
  - `EquityPoint = {date, cum_pnl, cum_pnl_pct}`，按持仓退出日期累计盈亏
  - 前端：新建 `EquityCurve.tsx`，使用 Recharts AreaChart 渲染
  - 盈利区域绿色半透明，亏损区域红色半透明，y=0 参考线
  - 放在统计概览页核心结果卡片上方

- **股票维度盈亏表**（Symbol Summary）
  - 后端：`StatsResponse` 新增 `symbol_summary: list[SymbolSummaryItem]` 字段
  - `SymbolSummaryItem = {symbol, trade_count, win_count, win_rate, total_pnl, avg_holding_days, first_trade_date, last_trade_date}`
  - 按个股汇总，仅统计 `cost_known=True` 的有效持仓（与 KPI 口径一致）
  - 前端：新建 `SymbolSummaryTable.tsx`，可排序表格，5 列
  - 默认按总盈亏降序，放在核心结果下方、进阶分析上方

- **AI Prompt 扩充**
  - `build_user_prompt()` 新增「风险指标」板块：profit_factor、expectancy、max_drawdown、max_drawdown_pct、consecutive_losses、avg_mae、avg_mfe、profit_capture_ratio、total_return_pct（共 10 项）
  - 新增「关键交易」板块：盈利 TOP3 + 亏损 TOP3
  - `_build_analysis_data()` 新增 `stats_data` 参数，从 StatsResponse 直接采集风险指标
  - Validator 新增 PF / max_drawdown_pct / consecutive_losses 软校验（±1% 容忍度）

- **测试**：`test_prompt.py` 新增 4 个测试，`test_validator.py` 新增 6 个测试（共 30 passed, 0 failed）

- **基础设施**：`.gitattributes`（统一行尾为 LF）、`vite.config.ts` 新增 `/api` proxy

### 变更

- `frontend/src/api/client.ts` BASE_URL 从 `http://localhost:8000` 改为 `""`（配合 vite proxy）
- `StatsCards.tsx` 集成 EquityCurve 和 SymbolSummaryTable 组件

---

## [V0.5.0] — 2026-06-25

### 新增

- **匿名案例贡献**：用户可提交匿名交割单用于产品改进，`entry_count` 修复，注册提示优化
- **设计令牌体系**：建立 CSS 变量基础，ToastContext / Layout / 认证 / 上传 / 分析面板全站组件迁移
- **ConfirmDialog** 焦点陷阱 / ESC 关闭 / 滚动锁定，提升无障碍体验
- **跨平台重启脚本** `restart.ps1`：PowerShell 原生实现，健康检查绕过代理，支持 Windows/Linux/macOS

### 变更

- **项目改名**：TradingJournalAnalyzer → TradeDoctor
- **部署流程重构**：服务器不再 git pull，改用本地 rsync 全量同步代码；新增 `server-setup.sh` 首次安装脚本 + nginx 配置模板
- **交割单存储**：文件从数据库 BLOB 迁移到磁盘存储，`.gitignore` 排除 `uploads/`
- **归因分析重构**：BREAKOUT 从 behavior 归位到 market_env（与 BREAKDOWN 对称），S14 区分 PnL 量级分桶与 outcome 行为标签，散户体验优化
- 统一后端端口为 8000，同步 vite proxy 和 restart 脚本
- `.env.example` 环境变量模板，`config.py` 绝对路径加载 `.env`
- `requirements.txt` 补全缺失依赖（pandas、slowapi、PyYAML）
- 前端标题与 SEO 描述更新，移除未使用的 WhatIfChart 组件

### 修复

- 修复 12 项高危缺陷（#11-#22）：手机号注册/上传报错、用户错误提示统一等
- 代码审查修复：3 阻塞 + 11 建议 + 8 小改进
- 密码改用环境变量传递，pin ssh-action SHA 防供应链攻击

---

## [V0.3.1] — 2026-06-22

### 修复

- 第三轮代码审查：8 阻塞 + 10 建议 + 4 小改进全量修复
- 前端 UI/UX 全面优化

---

## [V0.2.5] — 2026-06-20

### 新增

- `max_drawdown_pct`：最大回撤百分比（行业标准，对照 TradesViz/Edgewonk）
- `total_return_pct`：总收益率百分比
- `avg_win_pct` / `avg_loss_pct`：平均盈亏百分比

### 变更

- `is_small_sample` 字段：交易笔数 <5 时标记小样本，前端显示「样本不足」不评价

---

## [V0.2.3] — 2026-06-19

### 修复

- 真实券商导出适配（三层污染修复）：
  - GBK 编码探测（utf-8 → gb18030 → gbk）
  - 伪 `.xls` 文本格式回退（`read_excel` 失败后自动切换文本读取 + 分隔符探测）
  - `="..."` 外壳剥离（`_strip_formula_strings`）
  - 费用列 QUANTITY 守卫误杀修复（名称含费用关键词的列豁免）
- 新增 `tests/test_parsers/test_citic_xls.py` 固化真实 CITIC 特征为回归测试

---

## [V0.1.3] — 2026-06-15

### 新增

- **Expectancy（R-multiple）**：基于 pnl_pct 的预期收益，对照 TradesViz 标准
- **Shapley 归因**：公平归因各行为标签对总盈亏的贡献
- `baseline_expectancy` 字段用于标签对比

---

## [V0.1.2] — 2026-06-12

### 新增

- **MAE/MFE 风险分析**：持仓期间最大不利变动（浮亏）和最大有利变动（浮盈）
- `profit_capture_ratio`：止盈效率（浮盈兑现率）
- `mae_winners` / `mae_losers`：分盈亏组的 MAE 均值

### 修复

- PnL 计算扣除买卖双边费用
- 多费用列汇总（佣金、印花税、过户费、其他杂费）
- SmartParser 列类型推断修复（证券代码误选为数量列、价格列误判为费用列）

---

## [V0.1.1] — 2026-06-10

### 新增

- **4 维行为标签体系**：市场环境 / 交易行为 / 交易结果 / 心理推测
- **SmartParser**：基于数据值推断列类型，零配置自动识别券商格式
- **FIFO 持仓重建**：前序持仓标记（`cost_known`），软删除支持（`is_deleted`）
- **What-If 止损回测**：使用持仓期间日线 low 判断盘中触发
- JWT 认证（邮箱/手机号注册，密码强度校验）
- 支持多文件上传和历史分析记录
