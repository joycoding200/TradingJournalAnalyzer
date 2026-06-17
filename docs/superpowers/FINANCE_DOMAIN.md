# 金融领域知识 — TradingJournalAnalyzer

> 所有分析相关开发必须参考本文档。
> 指标定义、标签边界、行业标准格式是这里最核心的三部分。

---

## 一、指标词典

### 1. 胜率 (Win Rate)
- **定义**: 盈利笔数 ÷ 总笔数（仅统计 cost_known=True 的完整交易）
- **公式**: `win_count / valid_count`
- **显示**: 百分比，如 `73.0%`
- **TradesViz 参照**: Win Rate

### 2. 总盈亏 (Total PnL)
- **定义**: 所有完整交易的盈亏之和（已扣除手续费）
- **公式**: `sum(p.pnl)`
- **显示**: 绝对金额 + 括号标注总收益率，如 `+4276.31（收益率 0.6%）`
- **总收益率公式**: `total_pnl / total_invested`，其中 `total_invested = sum(avg_entry_price × total_quantity)`
- **TradesViz 参照**: Net Profit + Return %

### 3. 最大回撤 (Max Drawdown)
- **定义**: 累计盈亏曲线从峰值到谷底的最大跌幅
- **公式**: 遍历按离场日排序的持仓，跟踪 `peak = max(peak, cum_pnl)`，`dd = peak - cum_pnl`
- **⚠️ 行业标准**: **必须显示百分比**，`max_dd_pct = max_dd / peak`（peak > 0 时）
- **显示**: 百分比 + 括号标注绝对金额，如 `29.6%（最大回撤金额 +1264.23）`
- **响应同时输出**: 绝对值 `max_drawdown` 与百分比 `max_drawdown_pct` 二者并存
- **评级**: <10% 优秀 / 10-20% 正常 / >20% 高风险
- **TradesViz 参照**: Max Drawdown %

### 4. 盈亏比 (Profit Factor / PF)
- **定义**: 总盈利 ÷ 总亏损
- **公式**: `PF = sum(盈利仓位的 pnl) / abs(sum(亏损仓位的 pnl))`
- **⚠️ NOT**: win_rate / (1 - win_rate) — 这是胜率赔率，不是 PF
- **显示**: 比率 + 评级，如 `2.38（良好，>1.5 合格）`
- **评级**: ≥3 优秀 / ≥1.5 良好 / ≥1 合格 / <1 不合格
- **TradesViz 参照**: Profit Factor

### 5. 预期收益 (Expectancy / R-Multiple)
- **定义**: 每笔交易的平均预期收益率
- **公式**: `win_rate × avg_win_pct - (1 - win_rate) × avg_loss_pct`
- **⚠️ 必须用 pnl_pct（收益率），不能用 pnl（绝对金额）**
- **显示**: 百分比 + 评级，如 `1.0%（正期望）`
- **评级**: >2% 优秀 / >0 正期望 / ≤0 负期望
- **TradesViz 参照**: Expectancy (R)

### 6. 损益比 (Payoff Ratio)
- **定义**: 平均单笔盈利 ÷ 平均单笔亏损（绝对值）
- **公式**: `avg_win_amount / abs(avg_loss_amount)`
- **代码字段名**: `win_loss_ratio`（语义即 Payoff Ratio，API 响应字段用 win_loss_ratio）
- **显示**: 比率，如 `0.87`
- **TradesViz 参照**: Payoff Ratio / Avg Win/Avg Loss

### 7. 平均盈利 / 平均亏损
- **定义**: 盈利仓位的平均盈亏 / 亏损仓位的平均盈亏
- **显示**: 金额 + 括号标百分比，如 `+245.56（平均 +1.4%/笔）`
- **TradesViz 参照**: Avg Win / Avg Loss

### 8. 最大回撤容忍度 (MAE — Maximum Adverse Excursion)
- **定义**: 持仓期间从入场价计算的最大浮亏百分比（基于日线 low）
- **公式**: `min((bar_low - entry_price) / entry_price for each day in holding period)`
- **显示**: 百分比 + 评级，如 `-12.6%（风险较高）`
- **评级**: <-10% 风险较高 / -5%~-10% 风险可控 / >-5% 回撤较小
- **TradesViz 参照**: MAE %

### 9. 最大浮盈 (MFE — Maximum Favorable Excursion)
- **定义**: 持仓期间从入场价计算的最大浮盈百分比（基于日线 high）
- **公式**: `max((bar_high - entry_price) / entry_price for each day in holding period)`
- **显示**: 百分比，如 `78.0%`
- **TradesViz 参照**: MFE %

### 10. 止盈效率 (Profit Capture Ratio)
- **定义**: 交易者将浮盈兑现为实际盈利的能力
- **公式**: `mean(pnl_pct / mfe_pct) for each winning trade`（per-position 均值，不是 sum/sum）
- **⚠️ NOT**: `sum(pnl) / sum(MFE)` — 这会被大 MFE 交易主导
- **显示**: 百分比 + 评级，如 `20.4%（一般 — 平均兑现20%浮盈）`
- **评级**: ≥50% 优秀 / ≥30% 良好 / ≥15% 一般 / <15% 较差
- **TradesViz 参照**: Profit Capture / MFE Efficiency

### 11. 平均持仓天数
- **定义**: 入场日期到离场日期的日历天数
- **显示**: 天数，如 `1.3天（盈利 2天 / 亏损 1天）`

### 12. 连续亏损
- **定义**: 按期排序中最长的连续亏损笔数（pnl < 0 视为亏损）
- **显示**: 整数，如 `4次`

### 13. Shapley 归因（赚钱来源分析）
- **定义**: 用 Shapley Value 公平分配各标签对总盈亏的贡献
- **方法**: Monte Carlo 采样，保证各标签贡献之和 = 总 PnL
- **显示**: 标签名 + 金额 + 占比%，如 `熊市环境 +2004.34（46.9%）`
- **⚠️ 散户默认折叠**，标题"赚钱来源分析（公平归因，点击展开）"

### 14. 止损回测 (Stop Loss Backtest)
- **定义**: 假设设置 X% 止损，持仓期间日线 low 是否触达止损价
- **⚠️ 必须用持仓期间日线 low 判断**，不能用最终 PnL 判断
- **⚠️ 跳空低开处理**: `fill_price = min(open, stop_price)`（开盘价低于止损价时按开盘成交）
- **显示**: 止损参数 + 触发笔数 + 收益变化 + 结论

---

## 二、行为标签定义边界

### 市场环境维度 (market_env)

| 标签 | 定义 | 是 | 不是 |
|------|------|-----|------|
| BULL_TREND | MA20 > MA60 且入场价 > MA20 | 牛市环境中的交易 | 趋势交易行为 |
| BEAR_TREND | MA20 < MA60 且入场价 < MA20 | 熊市环境中的交易 | 逆势交易 |
| BREAKDOWN | 离场价 < 过去20日最低价 | 破位离场 | — |

### 交易行为维度 (behavior)

| 标签 | 定义 | 正例 | 反例 |
|------|------|------|------|
| CHASE | 5日涨幅>15% + 入场价>MA20×1.10 + 入场价≥20日高点×0.97 | 动量追涨 | 正常买入 |
| BOTTOM | 5日跌幅>15% + MA20<MA60 | 下跌趋势中买入 | 回调后正常加仓 |
| BREAKOUT | 入场价>过去20日最高价 + 成交量>20日均量×1.5（缺量数据时置信度降为 0.5） | 突破买入 | 小幅新高 |
| PYRAMID | 已有持仓时以更高价格加仓（加仓价>首次买入均价×1.02） | 加仓时已有未平仓位 | 首次开仓（即使后来盈利） |
| AVERAGE_DOWN | 已有亏损持仓时以更低价格加仓（加仓价<首次买入均价×0.95，且前序持仓处于亏损） | 亏损状态下补仓 | 盈利回调后加仓 |
| TURN | 同日既有买入又有卖出（或 entry_date==exit_date） | 日内做T | — |
| SCALP | 持仓 < 3天 | 超短线 | — |
| SWING | 持仓 3-30天 | 波段 | — |
| POSITION | 持仓 > 30天 | 长线持有 | — |
| FOMO | 5日内≥3天上涨 + 入场价≥当日最高价×0.98 | 追高情绪交易 | — |

### 交易结果维度 (outcome)

| 标签 | 定义 | ⚠️ 重要说明 |
|------|------|------------|
| TIGHT_STOP | 亏损2-5% + 持仓≤3天 | 这只是结果分类，不能确定是否真的设了止损 |
| TRAILING_STOP | 持仓>10天 + 0<盈利≤10% | 这不是移动止损行为，只是结果特征 |
| TIME_EXIT | 持仓>30天 + 盈亏绝对值<5% | 时间驱动的离场 |
| LARGE_LOSS_EXIT | 亏损>20% | 结果分类，不是行为分析 |

### 心理推测维度 (psychology)

| 标签 | 置信度 | 触发条件 |
|------|--------|----------|
| POSSIBLE_REVENGE | 0.3 | 重大亏损后24h内开仓，仓位更大 |
| OVERTRADING | 0.5 | 单日开仓数 > 均值+2σ |
| HOLD_LOSER | 0.5 | 持仓中位数: 亏损 > 盈利×1.5 |
| CUT_WINNER | 0.5 | 持仓中位数: 盈利 < 亏损×0.5 |
| PSY_FOMO | 0.3 | 连续3次买入价格递增 |

---

## 三、数据源规范

1. **行情数据**: mootdx (通达信 TCP 7709)，不封 IP
2. **行情缓存**: 日线落库到 `DailyBar` 表（含 open/high/low/close/volume + ma5/ma10/ma20/ma60 + avg_volume_20d）。`ensure_market_data()` 先查 DB 缓存，命中即跳过 mootdx 拉取；并发锁防止同一 symbol 被并行拉取
3. **均线计算**: 拉取时计算 MA5/MA10/MA20/MA60，基于日线 close，存入 DailyBar
4. **前复权**: 当前未使用复权数据。如未来支持，需在 `market_fetcher.py` 中启用

---

## 四、UI 规范

1. **所有指标显示必须中文优先**，英文缩写放括号内解释
2. **散户可理解性优先于专业精确性** — 如果散户看不懂一个指标，加一句人话解释
3. **信息分层**: 核心结果 > 进阶分析 > 高级分析（折叠）
4. **每个指标必须有评级**（优秀/良好/一般/较差），让小散户一眼能判断好坏
5. **小样本（<5笔）不评价**，显示"样本不足，暂不评价"

---

## 五、专业软件对照

| 本项目 | TradesViz | Edgewonk | Tradervue |
|--------|-----------|----------|-----------|
| 胜率 | Win Rate | Win Rate | Win % |
| 盈亏比(PF) | Profit Factor | Profit Factor | Profit Factor |
| 预期收益 | Expectancy | Expectancy | Avg Trade |
| 损益比 | Payoff Ratio | Payoff Ratio | W/L Ratio |
| 最大回撤 | Max Drawdown % | Max DD % | Max DD |
| 最大回撤容忍度(MAE) | MAE | MAE | MAE |
| 最大浮盈(MFE) | MFE | MFE | MFE |
| 止盈效率 | MFE Efficiency | Capture Rate | — |
