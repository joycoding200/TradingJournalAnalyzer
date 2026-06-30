# AI 输入字段契约（AI_INPUT_CONTRACT）

> 所有修改 AI 报告生成（`app/ai/prompt.py`、`app/api/report.py` 的 `_build_analysis_data`）的开发，必须先读本文件。
>
> 本文件是 `FINANCE_DOMAIN.md`（指标词典，全集）的子集契约——回答"系统算出的指标里，**哪些**喂给 AI、按**什么格式**渲染、依据**什么原则**筛选"。

## 为什么需要这份契约

历史上"哪些字段喂给 AI"是 V4.0 时按需零散加出来的，没有全局视图，导致两类系统性缺陷：

1. **采集/渲染脱节**：`win_loss_ratio`、`pnl_distribution` 进了 `analysis_data` 却没在 `build_user_prompt` 渲染——数据算了等于白算（已修复）。
2. **维度漏报**：优势/风险清单只按总盈亏绝对额排序，挤掉小额高效的标签（OVERTRADING 单笔 +13.08%）；且无"维度覆盖"约束，psychology 维度标签被 AI 自由裁量忽略（已通过 prompt 修复，本契约用字段层兜底）。

本契约把"采集层"和"渲染层"用一份清单钉死：**进 `analysis_data` 的字段，`build_user_prompt` 必须渲染**（原则 1）。

---

## 五条筛选原则

| # | 原则 | 说明 |
|---|------|------|
| 1 | **采集=渲染一致** | 任何进 `analysis_data` 的 key，`build_user_prompt` 必须有对应渲染分支。新增字段须同步改两处，缺一不可。 |
| 2 | **聚合优先于明细，单值优先于序列** | LLM 用不了图表/列表序列（`equity_curve`、`positions` 全列表不喂）。只喂单值或短摘要。 |
| 3 | **护栏字段必传** | `is_small_sample`、`baseline_expectancy` 必须喂，防 AI 对小样本乱评价、缺基准线判优劣。 |
| 4 | **维度覆盖** | `patterns` 喂全四维扁平列表，渲染时标注每标签所属维度，防 AI 漏看某维度。 |
| 5 | **系统算好的优先于让 AI 猜** | PF / expectancy / shapley 等用系统计算值，prompt 中带口径说明，禁止 AI 自行推算易错指标。 |

---

## 字段清单（四层）

每层标注：来源 schema / 渲染格式 / 状态（✅已有 / 🔧本次新增 / ❌不喂及理由）。

### 第 1 层：基础 KPI

| 字段 | 来源 | 渲染格式 | 状态 |
|------|------|----------|------|
| `total_trades` | analysis_data | `总交易笔数：N` | ✅ |
| `win_rate` | analysis_data | `胜率：X%` | ✅ |
| `total_pnl` | analysis_data | `总盈亏：±X` | ✅ |
| `avg_holding_days` | analysis_data | `平均持仓天数：N` | ✅ |

### 第 2 层：风险指标（来自 `stats_data`）

| 字段 | 来源 StatsResponse | 渲染格式 | 状态 |
|------|------|----------|------|
| `profit_factor` | profit_factor | `盈亏比：X.XX` | ✅ |
| `win_loss_ratio` | win_loss_ratio | `损益比：X.XX` | ✅（本次补渲染） |
| `expectancy` | expectancy | `预期收益：X%` | ✅ |
| `max_drawdown` | max_drawdown | `最大回撤：X元` | ✅ |
| `max_drawdown_pct` | max_drawdown_pct | 同上括号 `(X%)` | ✅ |
| `consecutive_losses` | consecutive_losses | `最大连续亏损：N次` | ✅ |
| `avg_mae` | avg_mae | `平均最大不利变动：-X%` | ✅ |
| `avg_mfe` | avg_mfe | `平均最大有利变动：X%` | ✅ |
| `profit_capture_ratio` | profit_capture_ratio | `止盈效率：X%` | ✅ |
| `total_return_pct` | total_return_pct | `总收益率：X%` | ✅ |
| `pnl_distribution` | pnl_distribution | `盈亏量级分布：大盈N笔、…` | ✅（本次补渲染） |
| `is_small_sample` | is_small_sample | `样本量提醒：是/否（<5笔）` | 🔧 本次新增 |
| `avg_win_holding_days` | avg_win_holding_days | 盈利持仓对比行 | 🔧 本次新增 |
| `avg_loss_holding_days` | avg_loss_holding_days | 亏损持仓对比行 | 🔧 本次新增 |

### 第 3 层：行为与归因

| 字段 | 来源 | 渲染格式 | 状态 |
|------|------|----------|------|
| `patterns` | InsightResponse.patterns | `标签(N维): X次, 胜率Y%, 总盈亏±Z, 单笔均收益±W%` | ✅（单笔均收益本次补） |
| `baseline_expectancy` | InsightResponse.baseline_expectancy | `整体预期收益基准：X%` | 🔧 本次新增 |
| `what_if` | WhatIfResponse.items | `移除X: delta ±Y, 影响度Z`（带口径说明） | ✅（口径本次补） |
| `shapley` | WhatIfResponse.shapley | `赚钱来源：标签 +X元 (Y%)` | 🔧 本次新增 |
| `positions_summary` | top/bottom3 positions | `盈利/亏损最多：symbol ±X (Y%), 持仓N天` | ✅ |
| `scenario_backtest` | report.py `_build_analysis_data` 采集（5个规则） | `规则名: 触发N次, delta ±X, 模拟后收益率±Y`（独立成段，带口径说明） | 🔧 V1.2.3 新增 |

### 第 4 层：不喂（及理由）

| 字段 | 不喂理由 |
|------|----------|
| `equity_curve` | 图表序列，LLM 无法消费，前端 Recharts 用 |
| `positions`（全列表） | 明细过大，只喂 top/bottom3 摘要 |
| `total_positions` / `unknown_cost_count` | 次要统计，无诊断增量 |
| `mae_winners` / `mae_losers` | avg_mae 已够用，分盈亏浮亏过细 |
| `best_pattern` / `worst_pattern` | 冗余，AI 可从 patterns 自行排序 |
| `cross_analysis` | 组合数不定，prompt 易变长；稳健档暂不喂，后续按需评估 |
| ~~`stop_loss` 止损回测~~ | **V1.2.3 已喂**（升格为 `scenario_backtest` 段，含 5 个规则：固定止损/大亏止损/移动止损/固定止盈/移动止盈）。注意其 delta 语义与 `what_if` 相反（应用规则 vs 移除行为），必须独立成段，口径说明成对出现 |

---

## 维护规则

1. **新增字段三同步**：改 `report.py` 的 `_build_analysis_data`（采集）→ 改 `prompt.py` 的 `build_user_prompt`（渲染）→ 改本契约（清单 + 原则核验）。
2. **口径说明成对出现**：凡含正负号易读反的字段（`what_if.delta`、未来 `stop_loss.delta`），渲染时必须配口径说明行（参见当前 whatif 段）。
3. **低置信度标注**：psychology 维度标签（PSY_ 前缀）渲染时属 psychology 维度，prompt 已规定 AI 须标"（推测，置信度低）"。
4. **小样本护栏**：`is_small_sample=True` 时，prompt 应引导 AI 对 <5 笔标签显示"样本不足"，对应 `FINANCE_DOMAIN.md` §四规范。

---

## 与其他文档的关系

- `FINANCE_DOMAIN.md`：指标**词典**（全集定义），本契约是其喂给 AI 的**子集**。
- `PROJECT_EXPERIENCE.md` 经验3：数据流来源说明，本契约是经验3的完整化。
- `VERIFICATION_CHECKLIST.md`：开发自检清单，应新增一项"采集/渲染一致性"自检。
