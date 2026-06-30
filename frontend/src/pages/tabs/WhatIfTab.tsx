import { LoadingSpinner, ErrorBox, Card, EmptyState, Collapsible } from "../../components/ui";
import { ShapleyPanel } from "../../components/ShapleyPanel";
import { patternLabel, PATTERN_MODULES } from "../../constants/patterns";

interface WhatIfTabProps {
  whatIf: {
    isLoading: boolean;
    error: Error | null;
    data: any;
  };
}

/** Format yuan values in a human-readable way. */
function fmtYuan(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 10000) {
    return `${(v >= 0 ? "+" : "-")}${(abs / 10000).toFixed(1)}万`;
  }
  return `${(v >= 0 ? "+" : "-")}${abs.toFixed(0)}元`;
}

/** Format a ratio (delta / return) as a signed percentage. */
function fmtPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
}

export default function WhatIfTab({ whatIf }: WhatIfTabProps) {
  if (whatIf.isLoading) {
    return <LoadingSpinner text="加载回测数据..." />;
  }
  if (whatIf.error) {
    return <ErrorBox message="请先导入交易数据" />;
  }
  if (!whatIf.data?.items || whatIf.data.items.length === 0) {
    return <EmptyState icon="📊" message="暂无回测数据" />;
  }

  const { data } = whatIf;

  // ── 反事实归因：按 delta（移除后收益率变化）分组 ──────────────
  // delta = what_if_return − original_return
  // delta > 0：移除后收益率上升 → 该行为在拖累，少做能改善
  // delta < 0：移除后收益率下降 → 该行为在扛收益，别乱砍
  // 仅归因「交易行为」+「心理推测」——市场环境不可选、交易结果是事后分类
  const actionable = data.items.filter((i: any) => {
    const dim = PATTERN_MODULES[i.removed_pattern];
    return dim === "behavior" || dim === "psychology";
  });
  const sortedByDelta = [...actionable].sort((a: any, b: any) => b.delta - a.delta);
  const toCut = sortedByDelta.filter((i: any) => i.delta > 0).slice(0, 2);
  const toKeep = sortedByDelta.filter((i: any) => i.delta < 0).slice(-2).reverse();

  return (
    <div className="space-y-6">
      {/* ═══════════════════════════════════════════════════════════
          SECTION 0: 策略对比速览矩阵 — 首屏决策入口
          ═══════════════════════════════════════════════════════════ */}
      {(() => {
        const rows: Array<{ name: string; sim?: any }> = [
          { name: "现状（无纪律）" },
          { name: "固定8%止损", sim: data.stop_loss },
          { name: "仅大亏止损", sim: data.stop_loss_large_loss },
          { name: "移动止损8%", sim: data.trailing_stop },
          { name: "固定止盈10%", sim: data.take_profit },
          { name: "移动止盈5%/5%", sim: data.trailing_take_profit },
        ];
        const currentReturn = data.stop_loss?.original_return ?? 0;
        const rating = (delta: number) =>
          delta > 0.005 ? "良好" : delta < -0.005 ? "较差" : "一般";
        // 至少有1个模拟结果才显示矩阵
        if (!rows.some((r) => r.sim)) return null;
        return (
          <div>
            <h2 className="text-sm font-medium mb-3">🎯 策略对比速览</h2>
            <p className="text-xs mb-3 text-text-secondary">
              口径：变化 = 模拟值 − 现状值，正数=该规则在本笔数据上改善收益，负数=拉低。
            </p>
            <Card className="overflow-hidden p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-xs">
                    <th className="p-3 text-left">策略</th>
                    <th className="p-3 text-right">模拟后收益率</th>
                    <th className="p-3 text-right">变化</th>
                    <th className="p-3 text-right">触发</th>
                    <th className="p-3 text-right">评级</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.name} className="border-b border-border last:border-0">
                      <td className="p-3 font-medium">{r.name}</td>
                      <td className="p-3 text-right text-text-secondary">
                        {r.sim ? fmtPct(r.sim.what_if_return) : fmtPct(currentReturn)}
                      </td>
                      <td className={`p-3 text-right font-medium ${
                        !r.sim ? "text-text-secondary"
                          : r.sim.delta > 0 ? "text-success"
                          : r.sim.delta < 0 ? "text-danger"
                          : "text-accent"
                      }`}>
                        {r.sim ? `${r.sim.delta >= 0 ? "+" : ""}${(r.sim.delta * 100).toFixed(1)}%` : "—"}
                      </td>
                      <td className="p-3 text-right text-text-secondary">
                        {r.sim ? `${r.sim.affected_positions} 次` : "—"}
                      </td>
                      <td className="p-3 text-right text-xs text-text-secondary">
                        {r.sim ? rating(r.sim.delta) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        );
      })()}

      {/* ═══════════════════════════════════════════════════════════
          SECTION 1: Stop Loss Backtest — most actionable
          ═══════════════════════════════════════════════════════════ */}
      {data.stop_loss && (
        <div>
          <h2 className="text-sm font-medium mb-3">💡 止损效果模拟</h2>
          <p className="text-xs mb-3 text-text-secondary">
            假设每次开仓设置 8% 止损线（A 股散户标准档），盘中触发即卖出，你的收益会变成怎样。
          </p>
          <Card className="p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="font-medium">8% 止损线</span>
              <span className="text-xs text-text-secondary">
                触发 {data.stop_loss.affected_positions} 次
              </span>
            </div>
            <div className="flex justify-between text-sm mt-2 text-text-secondary">
              <span>当前收益: {(data.stop_loss.original_return * 100).toFixed(1)}%</span>
              <span>止损后: {(data.stop_loss.what_if_return * 100).toFixed(1)}%</span>
              <span className={data.stop_loss.delta >= 0 ? "text-success" : "text-danger"}>
                变化 {data.stop_loss.delta >= 0 ? "+" : ""}{(data.stop_loss.delta * 100).toFixed(1)}%
              </span>
            </div>
            <div className={`mt-3 border-t border-border pt-3 text-xs font-medium ${
              data.stop_loss.delta > 0.005 ? "text-success"
                : data.stop_loss.delta < 0 ? "text-danger"
                : "text-accent"
            }`}>
              {data.stop_loss.delta > 0.005
                ? `✅ 8% 止损在本笔数据上模拟值为 ${fmtPct(data.stop_loss.what_if_return)}，较现状 ${fmtPct(data.stop_loss.original_return)} 改善 ${fmtPct(data.stop_loss.delta)}——止损有效，触发 ${data.stop_loss.affected_positions} 次挽回了部分亏损`
                : data.stop_loss.delta < 0
                ? `⚠️ 8% 止损反而拉低收益（${fmtPct(data.stop_loss.delta)}）：盘中触发 ${data.stop_loss.affected_positions} 次，误杀的盈利大于挽回的亏损，建议放宽或改用移动止损`
                : `8% 止损净影响很小（${fmtPct(data.stop_loss.delta)}）：盘中触发 ${data.stop_loss.affected_positions} 次，止损挽回的大亏与误杀的盈利基本抵消，可作兜底风控`}
            </div>
          </Card>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════
          SECTION 1b: 大亏持仓止损模拟 — 只给大亏笔设止损会怎样
          ═══════════════════════════════════════════════════════════ */}
      {data.stop_loss_large_loss && (
        <div>
          <h2 className="text-sm font-medium mb-3">🩹 大亏止损模拟</h2>
          <p className="text-xs mb-3 text-text-secondary">
            假设只对最终大亏（亏损超 8%）的持仓设 5% 止损，盘中触发即卖出，其他持仓不变。这是针对「大亏离场」的真反事实——少亏多少才能翻盘。
          </p>
          <Card className="p-4">
            <div className="flex justify-between items-center mb-2">
              <span className="font-medium">仅大亏持仓设 5% 止损</span>
              <span className="text-xs text-text-secondary">
                触发 {data.stop_loss_large_loss.affected_positions} 笔大亏
              </span>
            </div>
            <div className="flex justify-between text-sm mt-2 text-text-secondary">
              <span>当前收益: {(data.stop_loss_large_loss.original_return * 100).toFixed(1)}%</span>
              <span>止损后: {(data.stop_loss_large_loss.what_if_return * 100).toFixed(1)}%</span>
              <span className={data.stop_loss_large_loss.delta >= 0 ? "text-success" : "text-danger"}>
                变化 {data.stop_loss_large_loss.delta >= 0 ? "+" : ""}{(data.stop_loss_large_loss.delta * 100).toFixed(1)}%
              </span>
            </div>
            <div className={`mt-3 border-t border-border pt-3 text-xs font-medium ${
              data.stop_loss_large_loss.delta > 0.005 ? "text-success"
                : data.stop_loss_large_loss.delta < 0 ? "text-danger"
                : "text-accent"
            }`}>
              {data.stop_loss_large_loss.delta > 0.005
                ? `✅ 仅给这 ${data.stop_loss_large_loss.affected_positions} 笔大亏设止损，收益率从 ${(data.stop_loss_large_loss.original_return * 100).toFixed(1)}% 改善到 ${(data.stop_loss_large_loss.what_if_return * 100).toFixed(1)}%——大亏是亏损主因，止损能切实挽回`
                : data.stop_loss_large_loss.delta < 0
                ? "⚠️ 止损反而让收益变差（可能大亏笔在止损位反弹后又下跌），建议结合趋势判断"
                : `仅对大亏笔设止损影响很小（${(data.stop_loss_large_loss.delta * 100).toFixed(1)}%），大亏多由突发跳空导致，盘中止损难以触发`}
            </div>
          </Card>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════
          SECTION 1c-e: 移动止损 / 固定止盈 / 移动止盈 三张卡片
          delta = 应用规则后收益率 − 现状值，正=改善，负=拉低
          ═══════════════════════════════════════════════════════════ */}
      {([
        { key: "trailing_stop", icon: "📈", title: "移动止损模拟", param: "跟踪最高价回撤 8%",
          desc: "假设用移动止损（止损价随持仓期间最高价上移，回撤 8% 触发卖出），过滤洗盘、锁定浮盈的效果。",
          improve: (d: any) => `✅ 移动止损 8% 在本笔数据上模拟值为 ${fmtPct(d.what_if_return)}，较现状 ${fmtPct(d.original_return)} 改善 ${fmtPct(d.delta)}——触发 ${d.affected_positions} 次中多数锁住了浮盈`,
          worsen: (d: any) => `⚠️ 移动止损反而拉低收益（${fmtPct(d.delta)}）：触发 ${d.affected_positions} 次中误杀偏多，你的持仓期间波动较大，8% 回撤阈值偏紧，可考虑放宽或结合趋势确认`,
          neutral: (d: any) => `移动止损 8% 净影响很小（${fmtPct(d.delta)}）：触发 ${d.affected_positions} 次，锁利与误杀基本抵消` },
        { key: "take_profit", icon: "🎯", title: "固定止盈模拟", param: "涨到 +10% 即卖",
          desc: "假设统一以 +10% 止盈（触及即卖，未触及按原退出），检验机械止盈会多赚还是少赚。",
          improve: (d: any) => `✅ 固定止盈 +10% 模拟值为 ${fmtPct(d.what_if_return)}，较现状 ${fmtPct(d.original_return)} 改善 ${fmtPct(d.delta)}——触发 ${d.affected_positions} 次，截断了部分回吐、锁住了利润`,
          worsen: (d: any) => `⚠️ 固定止盈反而拉低收益（${fmtPct(d.delta)}）：触发 ${d.affected_positions} 次中多数卖出后继续上涨，截断了本可继续的利润——你的止盈纪律整体合理，机械加码止盈边际收益为负`,
          neutral: (d: any) => `固定止盈 +10% 净影响很小（${fmtPct(d.delta)}）：触发 ${d.affected_positions} 次，止盈与错过基本抵消` },
        { key: "trailing_take_profit", icon: "🚀", title: "移动止盈模拟", param: "盈利5%后启动，回撤5%止盈",
          desc: "假设盈利达 5% 后启动移动止损保护利润（回撤 5% 才卖，未达 5% 不干预），让利润奔跑的效果。",
          improve: (d: any) => `✅ 移动止盈 5%/5% 模拟值为 ${fmtPct(d.what_if_return)}，较现状 ${fmtPct(d.original_return)} 改善 ${fmtPct(d.delta)}——触发 ${d.affected_positions} 次，让利润奔跑的同时保护了到手利润`,
          worsen: (d: any) => `⚠️ 移动止盈反而拉低收益（${fmtPct(d.delta)}）：触发 ${d.affected_positions} 次中，激活后遇跳空缺口击穿止损价，到手利润反而回吐——你的实际离场时机已不错，可考虑更紧的 trail 减少回吐`,
          neutral: (d: any) => `移动止盈 5%/5% 净影响很小（${fmtPct(d.delta)}）：触发 ${d.affected_positions} 次，多数持仓未达 5% 激活阈值` },
      ] as const).map((cfg) => {
        const sim = (data as any)[cfg.key];
        if (!sim) return null;
        return (
          <div key={cfg.key}>
            <h2 className="text-sm font-medium mb-3">{cfg.icon} {cfg.title}</h2>
            <p className="text-xs mb-3 text-text-secondary">{cfg.desc}</p>
            <Card className="p-4">
              <div className="flex justify-between items-center mb-2">
                <span className="font-medium">{cfg.param}</span>
                <span className="text-xs text-text-secondary">
                  触发 {sim.affected_positions} 次
                </span>
              </div>
              <div className="flex justify-between text-sm mt-2 text-text-secondary">
                <span>当前收益: {(sim.original_return * 100).toFixed(1)}%</span>
                <span>模拟后: {(sim.what_if_return * 100).toFixed(1)}%</span>
                <span className={sim.delta >= 0 ? "text-success" : "text-danger"}>
                  变化 {sim.delta >= 0 ? "+" : ""}{(sim.delta * 100).toFixed(1)}%
                </span>
              </div>
              <div className={`mt-3 border-t border-border pt-3 text-xs font-medium ${
                sim.delta > 0.005 ? "text-success"
                  : sim.delta < 0 ? "text-danger"
                  : "text-accent"
              }`}>
                {sim.delta > 0.005 ? cfg.improve(sim)
                  : sim.delta < 0 ? cfg.worsen(sim)
                  : cfg.neutral(sim)}
              </div>
            </Card>
          </div>
        );
      })}

      {/* ═══════════════════════════════════════════════════════════
          SECTION 2: 反事实归因 — 少做哪些能改善收益
          ═══════════════════════════════════════════════════════════ */}
      <div>
        <h2 className="text-sm font-medium mb-3">📋 少做哪些能改善收益</h2>
        <p className="text-xs mb-3 text-text-secondary">
          假设你没做过某种行为，整体收益率会变成多少。只看「交易行为」和「心理推测」——市场环境不可选、交易结果是事后分类，不作为归因。
        </p>

        {toCut.length > 0 && (
          <div className="mb-3">
            <div className="text-xs font-medium text-danger mb-2">⚠️ 少做这些能改善收益</div>
            {toCut.map((item: any) => (
              <Card key={item.removed_pattern} className="p-3 mb-2 border-l-2 border-l-danger">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium">{patternLabel(item.removed_pattern)}</span>
                  <span className="text-sm text-danger font-medium">{fmtPct(item.delta)}</span>
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  移除后收益率 {fmtPct(item.what_if_return)}（当前 {fmtPct(item.original_return)}）
                </div>
              </Card>
            ))}
          </div>
        )}

        {toKeep.length > 0 && (
          <div>
            <div className="text-xs font-medium text-success mb-2">💪 这些在帮你扛收益，别乱砍</div>
            {toKeep.map((item: any) => (
              <Card key={item.removed_pattern} className="p-3 mb-2">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium">{patternLabel(item.removed_pattern)}</span>
                  <span className="text-sm text-success font-medium">{fmtPct(item.delta)}</span>
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  移除后收益率 {fmtPct(item.what_if_return)}（当前 {fmtPct(item.original_return)}）
                </div>
              </Card>
            ))}
          </div>
        )}

        {toCut.length === 0 && toKeep.length === 0 && (
          <EmptyState icon="📊" message="暂无可归因的行为标签" />
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════════
          SECTION 3: Advanced — Shapley + Factor Contribution
          ═══════════════════════════════════════════════════════════ */}
      <Collapsible title="展开高级分析（Shapley 归因 + 因子贡献详情）">
        <div className="space-y-6 pt-2">
          {/* Shapley */}
          {data.shapley && data.shapley.length > 0 && (
            <ShapleyPanel data={data.shapley} />
          )}

          {/* Factor contribution detail */}
          <div>
            <h2 className="text-sm font-medium mb-2">因子贡献详情</h2>
            <p className="text-xs mb-3 text-text-secondary">
              每种行为「移除后收益率变化」（delta）为主、「净盈亏」（absolute_impact）为辅。delta 为正=该行为在拖累收益，为负=在扛收益。仅列出「交易行为」和「心理推测」——市场环境不可选、交易结果（如大亏离场）是事后分类，对它们做"移除"无意义，大亏的对策请看上方「大亏止损模拟」。
            </p>
            {data.items.filter((item: any) => {
              const dim = PATTERN_MODULES[item.removed_pattern];
              return dim === "behavior" || dim === "psychology";
            }).map((item: any) => (
              <Card key={item.removed_pattern} className="p-3 mb-2">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-sm font-medium">{patternLabel(item.removed_pattern)}</span>
                  <span className={`text-sm font-medium ${item.delta >= 0 ? "text-danger" : "text-success"}`}>
                    移除后 {fmtPct(item.delta)}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-text-secondary">
                  <span>净盈亏: {fmtYuan(item.absolute_impact)}</span>
                  <span>当前: {fmtPct(item.original_return)}</span>
                  <span>剔除后: {fmtPct(item.what_if_return)}</span>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </Collapsible>
    </div>
  );
}
