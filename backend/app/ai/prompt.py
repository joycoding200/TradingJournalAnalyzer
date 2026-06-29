"""Prompt templates for the AI trading coach."""

SYSTEM_PROMPT = """你是 TradeDoctor（交易诊断助手）的 AI 交易教练。你的任务是基于用户的交易数据，生成一份《交易行为诊断书》。

## 数据真实性规范（极其重要 — 违反将导致报告被拒绝）

**绝对禁止编造以下任何信息。如果数据中不存在，就写"无相关数据"而不是猜测：**

1. **日期**：用户提示词中已提供"诊断日期（今天）"和"数据范围"，必须原样使用，不得加减天数。如果数据范围是多段（如"2026-01-01 至 2026-03-31、2026-06-01 至 2026-06-19"），表示用户上传了多个不连续的交割单，报告中也必须原样列出多段范围。
2. **交易者身份**：不要写"[用户]"、"匿名用户"、"交易员"等。直接省略交易者ID这一行，从分析周期开始写。
3. **股票名称**：系统只提供6位代码（如 600330、000901），**绝对禁止**根据代码猜测股票名称。报告中使用代码即可，不要添加名称。
4. **百分比数值**：报告中的每一个百分比都必须来自用户提示词中的数据。**绝对禁止**自行计算或推断任何百分比（如"亏损超过100%"、"赚了50%"等），除非该数字明确出现在提示词中。
5. **账户总资金/总投入**：如果没有提供，禁止猜测"总资金约X元"。
6. **具体天数/日期**：不要估算"约5-6个月"、"大约半年"等模糊时间。直接使用提供的起止日期。
7. **行为标签翻译**：数据中的模式名称是英文代码（如 CHASE、LARGE_LOSS_EXIT），报告中必须翻译为中文（如"追涨买入"、"大额亏损退出"）。

## 核心原则
1. **只分析行为，不预测市场。** 不推荐股票，不预测涨跌。
2. **基于数据说话。** 每一条结论都必须有数据支撑。
3. **建设性。** 指出问题的同时，给出可执行的改善建议。
4. **简明扼要。** 用简洁的段落呈现，避免冗长。
5. **面向散户。** 假设读者是一个炒股 3-5 年的老股民，不是金融科班出身，也不是小白。用茶馆聊天、股友交流的口吻写，三句话以内说清楚一件事。避免"建议您"、"请注意"等公文腔，直接用"你"。
6. **效率优先于规模。** 评价一个标签好坏时，单笔平均收益率（效率）比总盈亏绝对额更能反映交易质量。高效率的小额标签也要纳入，不要被大额低效标签挤掉。
7. **区分确定结论与低置信度推测。** 数据中标签分四维度：交易行为/市场环境/交易结果是可观测事实；心理推测维度（标签名含 PSY_ 前缀，如 PSY_FOMO，置信度低）是统计推断。心理推测可在报告中提及，但必须明确标注"（推测，置信度低）"，不得当作确定结论。

## 语言要求（重要）
- **必须全部使用中文输出。** 禁止在正文中使用英文术语、英文缩写或中英混杂。
- 所有指标必须附带中文解释（例：盈亏比即赚的钱除以亏的钱，大于1表示整体盈利）。
- 所有英文缩写首次出现时必须替换为中文全称（例：用"最大不利变动"替代"MAE"，用"最大有利变动"替代"MFE"）。

## 输出结构
### 核心结论
一句话概括当前交易状态。

### 优势清单
你做得好的交易行为（覆盖各维度中有代表性的盈利标签，优先纳入单笔平均收益率最高即效率最高的，不要只按总盈亏绝对额排序而漏掉小额高效的标签）。每条包含：
- 行为名称（中文，如：及时止损、顺势交易、仓位管理）
- 数据支撑（如：止损交易平均亏损仅 X%，远低于不止损交易）
- 一句话肯定

### 风险警示
最危险的交易行为（覆盖各维度中有代表性的亏损/拖累标签，优先纳入单笔平均亏损率最高即效率最差的，不要只按总盈亏绝对额排序而漏掉小额但低效的标签）。每条包含：
- 行为名称（中文）
- 数据支撑（如：该行为贡献了总亏损的 X%）
- 潜在原因推测
- 警示等级（⚠️ 注意 / 🔴 严重 / 🚨 高危）

### 改善建议
基于数据的 3-5 条具体可执行措施，每条必须是：
1. **一个具体动作**（如"单笔亏损超过总资金 2% 时强制止损"），不是泛泛的"控制风险"
2. **一个可量化目标**（如"将平均亏损控制在 X 元以内"），不是"少亏一些"
3. **一个执行触发条件**（如"持仓超过 X 天未盈利则重新评估"），不是"要有耐心"

建议格式：
> 建议一：[具体动作]
> 当前：[你的数据现状]
> 目标：[可量化的改善目标]
> 执行：[什么情况下触发此规则]"""


def build_user_prompt(analysis_data: dict) -> str:
    """Build a structured user prompt from analysis data.

    Args:
        analysis_data: Dict with keys:
            total_trades, win_rate, total_pnl, avg_holding_days,
            patterns (list of dicts with pattern_name, count, win_rate, total_pnl),
            what_if (list of dicts with removed_pattern, delta, contribution_pct).

    Returns:
        A formatted prompt string for the LLM.
    """
    # Get exact dates — NEVER let the AI guess
    report_date = analysis_data.get("report_date", "")
    date_range = analysis_data.get("date_start", "")  # now holds full segment string

    lines = [
        "请根据以下交易数据分析我的交易行为并生成诊断书。",
        "",
        f"诊断日期（今天）：{report_date}",
        f"数据范围：{date_range}",
        "",
        f"总交易笔数：{analysis_data.get('total_trades', 'N/A')}",
        f"胜率：{analysis_data.get('win_rate', 'N/A')}%",
        f"总盈亏：{analysis_data.get('total_pnl', 'N/A')}",
        f"平均持仓天数：{analysis_data.get('avg_holding_days', 'N/A')}",
        "",
        "行为标签统计：",
    ]

    patterns = analysis_data.get("patterns", [])
    if patterns:
        for p in patterns:
            avg = p.get("avg_pnl_pct")
            avg_str = f", 单笔均收益{avg * 100:+.2f}%" if avg is not None else ""
            dim = p.get("dimension")
            dim_str = f" [{dim}]" if dim else ""
            lines.append(
                f"- {p['pattern_name']}{dim_str}: {p['count']}次, "
                f"胜率{p['win_rate']:.1%}, 总盈亏{p['total_pnl']:+.2f}{avg_str}"
            )
    else:
        lines.append("（暂无行为标签数据）")

    lines.append("")
    lines.append("反事实回测（What If）：")
    lines.append("口径：delta = 移除该行为后的收益率 − 原始收益率。")
    lines.append("delta 为负 = 移除后少赚，该行为【在帮你赚钱】（利润来源）；")
    lines.append("delta 为正 = 移除后更赚，该行为【在亏钱】（拖累表现）。")
    lines.append("正负号代表方向，不可把负数说成“收益增加”。")
    what_if = analysis_data.get("what_if", [])
    if what_if:
        for w in what_if:
            lines.append(
                f"- 移除 {w['removed_pattern']}: delta {w['delta']:+.4f}, "
                f"影响度 {w['contribution_pct']:.2f}"
            )
    else:
        lines.append("（暂无回测数据）")

    # AI_INPUT_CONTRACT: 赚钱来源归因（Shapley，各行为对总盈亏的公平贡献，之和=总盈亏）
    shapley = analysis_data.get("shapley")
    if shapley:
        lines.append("")
        lines.append("赚钱来源分析（Shapley 归因，各行为对总盈亏的公平贡献）:")
        for s in shapley:
            lines.append(
                f"- {s['pattern_name']}: {s['shapley_value']:+.2f}元 "
                f"({s['pct_of_total']:+.1f}%)"
            )

    # V4.0: risk metrics section
    if any(k in analysis_data for k in ("profit_factor", "max_drawdown", "expectancy")):
        lines.append("")
        lines.append("风险指标：")
        # AI_INPUT_CONTRACT 护栏：小样本提醒（<5笔），低于此数不评价标签好坏
        if analysis_data.get("is_small_sample"):
            lines.append("- ⚠️ 样本不足（有效交易<5笔）：以下指标仅供参考，不据此评价行为好坏")
        bl = analysis_data.get("baseline_expectancy")
        if bl is not None:
            lines.append(f"- 整体预期收益基准（评价各行为盈亏的基准线，>0为正期望）: {bl}%")
        pf = analysis_data.get("profit_factor")
        lines.append(f"- 盈亏比（赚的钱÷亏的钱，>1表示整体盈利）: {'∞（无亏损交易）' if pf is None else f'{pf:.2f}'}")
        wlr = analysis_data.get("win_loss_ratio")
        if wlr is not None:
            lines.append(f"- 损益比（平均单笔盈利÷平均单笔亏损，>1表示赚多亏少）: {wlr:.2f}")
        expect = analysis_data.get("expectancy")
        if expect is not None:
            lines.append(f"- 预期收益（每笔交易的平均预期盈亏百分比）: {expect}%")
        dd = analysis_data.get("max_drawdown")
        ddpct = analysis_data.get("max_drawdown_pct")
        if dd is not None and ddpct is not None:
            lines.append(f"- 最大回撤（账户从最高点回落的最大幅度）: {dd}元 ({ddpct * 100:.1f}%)")
        cl = analysis_data.get("consecutive_losses")
        if cl is not None:
            lines.append(f"- 最大连续亏损（连续亏损的最多笔数）: {cl}次")
        # AI_INPUT_CONTRACT: 盈亏持仓天数对比 — 诊断"死扛"（亏损持仓>盈利持仓说明小亏拖成大亏）
        awh = analysis_data.get("avg_win_holding_days")
        alh = analysis_data.get("avg_loss_holding_days")
        if awh is not None and alh is not None:
            lines.append(f"- 持仓天数对比（盈利单{awh}天 / 亏损单{alh}天，亏损持仓更久=有死扛倾向）")
        mae = analysis_data.get("avg_mae")
        if mae is not None:
            lines.append(f"- 平均最大不利变动（持仓期间浮亏的最大幅度）: {mae * 100:.1f}%")
        mfe = analysis_data.get("avg_mfe")
        if mfe is not None:
            lines.append(f"- 平均最大有利变动（持仓期间浮盈的最大幅度）: {mfe * 100:.1f}%")
        pcr = analysis_data.get("profit_capture_ratio")
        if pcr is not None:
            lines.append(f"- 止盈效率（最终获利÷最高浮盈，越高越能拿住利润）: {pcr * 100:.1f}%")
        tr = analysis_data.get("total_return_pct")
        if tr is not None:
            lines.append(f"- 总收益率: {tr * 100:.1f}%")
        pnl_dist = analysis_data.get("pnl_distribution")
        if pnl_dist:
            dist_str = "、".join(f"{d['level']}{d['count']}笔" for d in pnl_dist)
            lines.append(f"- 盈亏量级分布（按单笔盈亏幅度分桶）: {dist_str}")

    # V4.0: key trades section
    ps = analysis_data.get("positions_summary")
    if ps:
        lines.append("")
        lines.append("关键交易：")
        top_winners = ps.get("top_winners", [])
        if top_winners:
            lines.append("- 盈利最多:")
            for w in top_winners:
                lines.append(
                    f"  • {w['symbol']}: {w['pnl']:+.2f} ({w['pnl_pct'] * 100:.1f}%), "
                    f"持仓{w['holding_days']}天 ({w['entry_date']} → {w['exit_date']})"
                )
        top_losers = ps.get("top_losers", [])
        if top_losers:
            lines.append("- 亏损最多:")
            for l in top_losers:
                lines.append(
                    f"  • {l['symbol']}: {l['pnl']:+.2f} ({l['pnl_pct'] * 100:.1f}%), "
                    f"持仓{l['holding_days']}天 ({l['entry_date']} → {l['exit_date']})"
                )

    lines.append("")
    lines.append("请按照系统提示的格式输出《交易行为诊断书》。")
    lines.append("注意：报告中不要包含'交易者ID'这一行；诊断日期使用上面提供的日期；股票只用代码不要加名称；所有数字必须来自以上数据。")

    return "\n".join(lines)
