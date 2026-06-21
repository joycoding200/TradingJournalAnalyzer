# 指标口径审查报告 — TradingJournalAnalyzer

**审查人**：投资研究员（finance-investment-researcher）
**审查对象**：6 层数据管道的指标计算层（position / insight / whatif / mae / analysis API）
**对照基准**：TradesViz / Edgewonk / Tradervue（详见 FINANCE_DOMAIN.md §五）+ CLAUDE.md 关键设计决策
**审查日期**：2026-06-20

---

## 执行摘要

整体口径**专业、自洽**，PF / Expectancy(R) / MAE / MFE / 止盈效率 / 止损回测等核心定义均与行业标准对齐，且在关键风险点（仓位规模偏置、止损回测只用最终 PnL、止盈效率被大 MFE 主导）上做了**有意识的防御性设计**。这是我见过的散户工具里少见的严谨度。

但审查发现 **3 个会误导决策的口径缺陷**（1 个高风险、2 个中风险）和若干一致性瑕疵。作为投资研究员，我最关心的是：**这些缺陷是否会让散户对一个亏损策略产生"正期望"的错觉，或低估尾部风险。**

---

## ✅ 口径正确的部分（逐一对照验证）

| 指标 | 代码位置 | 验证结论 |
|------|---------|---------|
| **Profit Factor** | `backend/app/api/analysis.py:230` `gross_profit/gross_loss` | ✅ 正确，**非** `win_rate/(1-win_rate)`，符合 CLAUDE.md 硬约束 |
| **Expectancy (R)** | `backend/app/engine/insight.py:32` `win_rate×avg_win_pct − (1−win_rate)×avg_loss_pct` | ✅ 用 `pnl_pct` 非 `pnl`，消除仓位规模偏置，符合 TradesViz Expectancy(R) |
| **止盈效率** | `backend/app/engine/mae.py:106-110` `mean(pnl_pct/mfe_pct)` | ✅ per-position 均值，**非** `sum/sum`，代码注释明确说明避免大 MFE 主导 — 这正是我会要求的设计 |
| **止损回测** | `backend/app/engine/whatif.py:158-169` 检查持仓期间日线 `low` | ✅ 真盘中触发判断，跳空低开 `fill_price=min(open, stop_price)`，符合 CLAUDE.md 硬约束 |
| **MAE/MFE** | `backend/app/engine/mae.py:52-53` 基于日线 low/high | ✅ 入场价基准，符合定义 |
| **PF=∞ / 最大亏损=--** | `frontend/src/components/StatsCards.tsx:107,87` | ✅ 100% 胜率场景前端兜底为 ∞，无亏损记录显示 -- |
| **cost_known 过滤** | `backend/app/engine/insight.py:106` / `backend/app/engine/whatif.py:41` | ✅ orphan sell（成本未知）排除出统计，避免污染胜率与归因 |

---

## 🔴 高风险发现：最大回撤百分比在"全程亏损"场景下报 0%，掩盖尾部风险

**位置**：`backend/app/api/analysis.py:236-247`

```python
peak = 0.0          # ← 初始峰值为 0
max_dd = 0.0
for p in sorted_positions:
    cum_pnl += p.pnl
    if cum_pnl > peak:
        peak = cum_pnl
    dd = peak - cum_pnl
    if dd > max_dd:
        max_dd = dd
max_drawdown_pct = (max_dd / peak) if peak > 0 else 0.0   # ← peak=0 时直接 0%
```

**问题**：`peak` 初始化为 0，只有当累计盈亏转正才会抬升。若一个账户从第一笔起就持续亏损（`cum_pnl` 全程为负），`peak` 永远是 0，于是：
- `max_dd` 会正确记录绝对回撤金额（因为 `dd = 0 − cum_pnl = |cum_pnl|`）
- 但 `max_drawdown_pct = 0/0 → 0.0`（被 `if peak > 0` 短路为 0）

**后果**：一个全程阴跌、累计亏损 30% 的账户，前端会显示「最大回撤 0%」——评级判为"优秀（<10%）"。这是**最危险的误导**：散户看到"回撤优秀"会加仓，而真实风险敞口被完全隐藏。FINANCE_DOMAIN.md §3 明确要求"必须显示百分比"，此处口径违反该硬约束。

**对冲论点（看多实现方）**：用累计盈亏曲线算 DD 本身是 TradesViz 口径，多数场景正确；问题仅在"全程未创新高"的退化路径上。

**建议修复**：以初始资金或首笔投入为分母兜底。
```python
peak = 0.0
max_dd = 0.0
baseline = 0.0  # 或 total_invested 作为资本基准
for p in sorted_positions:
    cum_pnl += p.pnl
    peak = max(peak, cum_pnl)
    dd = peak - cum_pnl
    max_dd = max(max_dd, dd)
# peak<=0 时，以首笔回撤前的资本基准做分母，避免 0%
denom = peak if peak > 0 else (total_invested or 1.0)
max_drawdown_pct = max_dd / denom if denom > 0 else 0.0
```
> 注：业界对"无初始资金语境下如何报 DD%"有分歧。 TradesViz 用账户权益曲线；本项目无账户总权益概念，用 `total_invested` 做兜底分母是可接受的近似，至少不会报 0%。

---

## 🟡 中风险发现 1：100% 胜率时后端 PF 返回 0.0，依赖前端兜底，存在单点失效

**位置**：`backend/app/api/analysis.py:230`
```python
profit_factor = total_gross_profit / total_gross_loss if total_gross_loss > 0 else 0.0
```
无亏损时后端返回 `0.0`，前端 `frontend/src/components/StatsCards.tsx:107` 用 `noLoss ? "∞"` 兜底。

**问题**：口径**分裂**在前后端。后端的 `0.0` 在语义上是"不合格"（评级 <1），但前端展示是"∞（优秀）"。任何绕过该前端组件的消费者（快照 `stats_snapshot` `analysis.py:279`、AI 报告输入、未来移动端）都会把 100% 胜率读成 PF=0，进而被 AI 解释器描述为"盈亏比不合格"——**与事实完全相反**。

**建议**：后端统一返回 `None`/`float('inf')`/特殊标记，由 schema 层序列化为 `"∞"`，让所有消费者一致。快照里也应存 `null` 而非 `0.0`。

---

## 🟡 中风险发现 2：平本交易（pnl=0）被计入"亏损"分母，扭曲胜率与 Expectancy

**位置**：`backend/app/api/analysis.py:219` 与 `backend/app/engine/insight.py:26`
```python
loss_positions = [p for p in valid_positions if p.pnl <= 0]   # ← pnl==0 归入亏损
```
平本（扣费后刚好为 0）的交易被算作亏损，会**压低胜率**、**抬高 avg_loss 的样本量但拉低 avg_loss 幅度**，进而影响 Expectancy(R)。

**对冲论点**：这在业界确实有两派。TradesViz 把 break-even 归入"非盈利"，Edgewonk 允许单独分类。本项目的选择不算错，但 FINANCE_DOMAIN.md §1 定义胜率为"盈利笔数 ÷ 总笔数"，未明确 0 值归属——**文档与代码的边界未闭合**。

**建议**：在 FINANCE_DOMAIN.md §1 明确「pnl==0 计入亏损分母」并说明理由（含手续费视角下平本即真实小亏），让口径可追溯而非靠代码隐式约定。

---

## ⚪ 低风险 / 一致性瑕疵

1. **归因 contribution_pct 用 `|delta|/max(|delta|)` 归一化**（`backend/app/engine/whatif.py:97-101`）：`WhatIfResponse.items`（反事实 leave-one-out）的 `contribution_pct` 是相对影响排序，**不是** Shapley 贡献。注意：这与 `backend/app/engine/attribution.py` 的 Shapley（Monte Carlo，已实现并在 `analysis.py:508` 接入 `WhatIfResponse.shapley`）是两套并存的归因。文档 §13 描述的 Shapley 已正确实现，**无需改名**；仅需在 UI 上区分"反事实归因（删某标签后收益变化）"与"Shapley 公平归因"两个面板的标题，避免散户混淆。

2. **止损回测 `loss_cap` 默认 0.05 但回测 PnL 未扣手续费**（`backend/app/engine/whatif.py:166`）：`simulated_pnl += exit_cost - entry_cost` 没减买卖佣金，而真实持仓 PnL 是扣过费的。基准与反事实口径不一致，会**高估止损策略的收益改善**。建议回测 PnL 也减去 `total_buy_comm + sell_comm`。

3. **分组重建 `build_grouped` 的 `pnl_pct = pnl/invested`，其中 `invested = total_buy_cost + total_buy_comm`**（`backend/app/engine/position.py:285,298`），而 FIFO 重建 `pnl_pct = pnl/(avg_entry*qty + total_buy_comm)`（`backend/app/engine/position.py:138`）。两者分母语义一致（成本+买入佣金）。
   - **【复查降级，无需改动】** 初稿曾标记"卖出佣金未进入分母"。复查后撤回：按 TradesViz/Edgewonk 标准 `PnL% = Net PnL / Cost Basis`，Cost Basis = 入场价×数量 + 入场佣金，卖出佣金作为 exit fee 在 Net PnL 分子扣除、**不进分母**。当前实现符合行业标准；若将卖出佣金加进分母反而会双重计算并偏离标准。

4. **`consecutive_losses` 按 `pnl < 0` 判定**（文档 §12），而上面 loss 用 `<= 0`——亏损边界在两个指标间不一致。建议统一。

---

## 论点破坏者（什么会改变我的判断）

- 若产品定位明确为"仅给已盈利账户复盘"，则 §最大回撤全程亏损场景的发生概率低，高风险降级为中风险——但 A 股散户恰恰是亏损账户为主，此假设不成立。
- 若 `stats_snapshot` 仅用于前端展示、且确认无其他消费者，则 PF=0 兜底问题降级——但 AI 解释器明确消费该输入，故维持中风险。

## 建议的修复优先级

| 优先级 | 项 | 工作量 |
|--------|-----|--------|
| P0 | 最大回撤百分比全程亏损报 0% | 小（改分母兜底 + 测试） |
| P1 | PF=∞ 后端返回 0 → 统一 null/inf | 小（schema + 快照） |
| P1 | 止损回测 PnL 未扣手续费 | 小 |
| P2 | 文档 §1 明确 pnl=0 归属；区分反事实归因与 Shapley 归因 UI 标题 | 文档 |
| P2 | 亏损边界 `<=0` vs `<0` 统一 | 小 |

---

**审查结论**：核心金融定义严谨、防御性设计到位，可作为机构级散户复盘工具的口径底座。但 **P0 最大回撤口径缺陷会在最危险的全亏损场景下给出"优秀"评级**，违背 CLAUDE.md 不可随意改动的金融定义，建议优先修复后再做下一轮功能迭代。
