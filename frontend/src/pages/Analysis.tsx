import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useStats, useInsight, useWhatIf, useRunAnalysis, useGenerateReport } from "../hooks/useAnalysis";
import StatsCards from "../components/StatsCards";
import PatternChart from "../components/PatternChart";
import WhatIfChart from "../components/WhatIfChart";
import { patternLabel, dimensionLabel, DIMENSION_ORDER } from "../constants/patterns";

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        style={{
          backgroundColor: "transparent", border: "none", cursor: "pointer",
          color: "var(--text-secondary)", fontSize: "13px", fontWeight: 500,
          padding: 0, marginBottom: open ? 12 : 0,
        }}
      >
        {open ? "▾ " : "▸ "}{title}
      </button>
      {open && <div>{children}</div>}
    </div>
  );
}

type Tab = "stats" | "insight" | "whatif";
type InsightDim = "market_env" | "behavior" | "outcome" | "psychology";

export default function Analysis() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>("stats");
  const [insightDim, setInsightDim] = useState<InsightDim>("behavior");

  const runAnalysis = useRunAnalysis();
  const stats = useStats(id);
  const insight = useInsight(id);
  const whatIf = useWhatIf(id);
  const genReport = useGenerateReport();

  const handleGenerateReport = () => {
    if (!id) return;
    genReport.mutate(id, {
      onSuccess: (data) => {
        navigate(`/report/${data.report_id}`);
      },
    });
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "stats", label: "统计概览" },
    { key: "insight", label: "归因分析" },
    { key: "whatif", label: "What If 回测" },
  ];

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">分析面板</h1>
        <button
          onClick={handleGenerateReport}
          disabled={genReport.isPending}
          style={{
            backgroundColor: "var(--success)",
            color: "#000",
            border: "none",
            borderRadius: "8px",
            padding: "8px 20px",
            cursor: genReport.isPending ? "not-allowed" : "pointer",
            opacity: genReport.isPending ? 0.6 : 1,
          }}
          className="text-sm font-medium"
        >
          {genReport.isPending ? "生成中..." : "生成 AI 报告"}
        </button>
      </div>

      <div className="flex gap-1 mb-6" style={{ borderBottom: "1px solid var(--border)" }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              backgroundColor: "transparent",
              border: "none",
              borderBottom: activeTab === tab.key ? "2px solid var(--accent)" : "2px solid transparent",
              color: activeTab === tab.key ? "var(--accent)" : "var(--text-secondary)",
              padding: "10px 16px",
              cursor: "pointer",
              marginBottom: "-1px",
            }}
            className="text-sm font-medium"
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "stats" && (
        <>
          {stats.isLoading && <div className="text-center py-8" style={{ color: "var(--text-secondary)" }}>加载中...</div>}
          {stats.error && <div className="text-center py-8" style={{ color: "var(--danger)" }}>加载失败</div>}
          {stats.data && <StatsCards stats={stats.data} />}
        </>
      )}

      {activeTab === "insight" && (
        <div className="space-y-6">
          {insight.isLoading && <div className="text-center py-8" style={{ color: "var(--text-secondary)" }}>加载中...</div>}
          {insight.error && <div className="text-center py-8" style={{ color: "var(--danger)" }}>请先导入交易数据</div>}
          {insight.data && (
            <>
              {/* Dimension sub-tabs */}
              <div className="flex gap-1" style={{ borderBottom: "1px solid var(--border)" }}>
                {DIMENSION_ORDER.map((dim) => (
                  <button
                    key={dim}
                    onClick={() => setInsightDim(dim as InsightDim)}
                    style={{
                      backgroundColor: "transparent",
                      border: "none",
                      borderBottom: insightDim === dim ? "2px solid var(--accent)" : "2px solid transparent",
                      color: insightDim === dim ? "var(--accent)" : "var(--text-secondary)",
                      padding: "8px 14px",
                      cursor: "pointer",
                      marginBottom: "-1px",
                    }}
                    className="text-xs font-medium"
                  >
                    {dimensionLabel(dim)}
                  </button>
                ))}
              </div>

              <div>
                <div style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }} className="overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        <th className="p-3 text-left">标签</th>
                        <th className="p-3 text-right">次数</th>
                        <th className="p-3 text-right">胜率</th>
                        <th className="p-3 text-right">预期值</th>
                        <th className="p-3 text-right">盈亏比(PF)</th>
                        <th className="p-3 text-left" style={{ maxWidth: 140 }}>评价</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(insight.data as any)[insightDim]?.map((p: any) => {
                        const isPos = p.expectancy > 0;
                        const baseline = (insight.data as any).baseline_expectancy || 0;
                        const pf = (p.gross_loss ?? 0) > 0 ? (p.gross_profit ?? 0) / (p.gross_loss ?? 1) : (p.gross_profit ?? 0) > 0 ? 999 : 0;
                        const isSmallSample = p.count < 5;

                        // Multi-dimension evaluation (V2.4)
                        let evalText: string, evalColor: string;
                        if (isSmallSample) {
                          evalText = `样本不足（${p.count}笔），暂不评价`;
                          evalColor = "var(--text-secondary)";
                        } else if (isPos && pf > 2) {
                          evalText = "优秀：正期望且显著优于均值，核心盈利模式";
                          evalColor = "var(--success)";
                        } else if (isPos && p.expectancy > baseline) {
                          evalText = "良好：优于均值，建议保持";
                          evalColor = "var(--success)";
                        } else if (isPos && p.expectancy <= baseline) {
                          evalText = "正收益但低于最佳模式，可优化";
                          evalColor = "var(--accent)";
                        } else {
                          evalText = "负期望：持续亏损，建议减少或改进";
                          evalColor = "var(--danger)";
                        }

                        return (
                          <tr
                            key={p.pattern_name}
                            style={{
                              borderBottom: "1px solid var(--border)",
                              backgroundColor: isPos ? "rgba(34,197,94,0.04)" : "rgba(239,68,68,0.04)",
                              opacity: isSmallSample ? 0.6 : 1,
                            }}
                          >
                            <td className="p-3 font-medium" style={{ color: isPos ? "var(--success)" : p.expectancy < 0 ? "var(--danger)" : "var(--text-primary)" }}>
                              {isSmallSample ? "" : isPos ? "✓ " : "✗ "}{patternLabel(p.pattern_name)}
                            </td>
                            <td className="p-3 text-right">{p.count}</td>
                            <td className="p-3 text-right" style={{ color: p.win_rate >= 0.5 ? "var(--success)" : "var(--danger)" }}>
                              {(p.win_rate * 100).toFixed(1)}%
                            </td>
                            <td className="p-3 text-right font-semibold" style={{ color: isPos ? "var(--success)" : "var(--danger)" }}>
                              {p.expectancy >= 0 ? "+" : ""}{(p.expectancy * 100).toFixed(1)}%
                            </td>
                            <td className="p-3 text-right" style={{ color: pf >= 1.5 ? "var(--success)" : pf >= 1 ? "var(--accent)" : "var(--danger)" }}>
                              {p.win_rate >= 1 ? "∞" : pf.toFixed(2)}
                            </td>
                            <td className="p-3 text-xs" style={{ color: evalColor, maxWidth: 160 }}>
                              {p.expectancy > baseline && !isSmallSample ? "↑ " : p.expectancy < baseline && !isSmallSample ? "↓ " : ""}{evalText}
                            </td>
                          </tr>
                        );
                      }) || (
                        <tr><td colSpan={6} className="p-3 text-center" style={{ color: "var(--text-secondary)" }}>无数据</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {insight.data.patterns?.length > 0 && (
                <PatternChart data={insight.data.patterns} />
              )}
            </>
          )}
        </div>
      )}

      {activeTab === "whatif" && (
        <>
          {whatIf.isLoading && <div className="text-center py-8" style={{ color: "var(--text-secondary)" }}>加载中...</div>}
          {whatIf.error && <div className="text-center py-8" style={{ color: "var(--danger)" }}>请先导入交易数据</div>}
          {whatIf.data?.items && whatIf.data.items.length > 0 ? (
            <div className="space-y-6">
              {/* V2.4 Shapley: collapsible "赚钱来源分析" */}
              {whatIf.data.shapley && whatIf.data.shapley.length > 0 && (
                <Collapsible title="赚钱来源分析（公平归因，点击展开）">
                  <p className="text-xs mb-3" style={{ color: "var(--text-secondary)" }}>
                    各标签对总收益的贡献占比，总和=100%，消除重复计算。
                  </p>
                  {whatIf.data.shapley.map((s: any) => (
                    <div key={s.pattern_name} className="mb-2">
                      <div className="flex justify-between text-xs mb-1">
                        <span>{patternLabel(s.pattern_name)}</span>
                        <span style={{ color: s.shapley_value >= 0 ? "var(--success)" : "var(--danger)" }}>
                          {s.shapley_value >= 0 ? "+" : ""}{s.shapley_value.toFixed(2)}（{s.pct_of_total}%）
                        </span>
                      </div>
                      <div style={{ backgroundColor: "var(--border)", borderRadius: 4, height: 6, overflow: "hidden" }}>
                        <div style={{
                          width: `${Math.abs(s.pct_of_total)}%`,
                          height: "100%",
                          backgroundColor: s.shapley_value >= 0 ? "var(--success)" : "var(--danger)",
                          borderRadius: 4,
                          transition: "width 0.3s",
                        }} />
                      </div>
                    </div>
                  ))}
                </Collapsible>
              )}

              {/* V2.4 Stop Loss with conclusion */}
              {whatIf.data.stop_loss && (
                <div>
                  <h2 className="text-sm font-medium mb-3">止损规则回测</h2>
                  <p className="text-xs mb-3" style={{ color: "var(--text-secondary)" }}>
                    遍历持仓期间每日最低价，判断是否盘中触及止损线。
                  </p>
                  <div style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }} className="p-4">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium">设置 5% 止损</span>
                      <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                        盘中触发 {whatIf.data.stop_loss.affected_positions} 笔
                      </span>
                    </div>
                    <div className="flex justify-between text-sm mt-2">
                      <span style={{ color: "var(--text-secondary)" }}>原始收益: {(whatIf.data.stop_loss.original_return * 100).toFixed(1)}%</span>
                      <span style={{ color: "var(--text-secondary)" }}>止损后: {(whatIf.data.stop_loss.what_if_return * 100).toFixed(1)}%</span>
                      <span style={{ color: whatIf.data.stop_loss.delta >= 0 ? "var(--success)" : "var(--danger)" }}>
                        Δ {whatIf.data.stop_loss.delta >= 0 ? "+" : ""}{(whatIf.data.stop_loss.delta * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="mt-3 pt-3 text-xs font-medium" style={{
                      borderTop: "1px solid var(--border)",
                      color: whatIf.data.stop_loss.delta > 0 ? "var(--success)"
                        : whatIf.data.stop_loss.delta < -0.03 ? "var(--danger)"
                        : "var(--accent)",
                    }}>
                      {whatIf.data.stop_loss.delta > 0
                        ? "✅ 结论：历史数据支持设置5%止损，可有效减少损失"
                        : whatIf.data.stop_loss.delta < -0.03
                        ? "⚠️ 结论：5%止损会严重损害收益（-2.3%），你的交易风格不适合机械止损，建议放宽至8-10%或采用移动止损"
                        : `结论：5%止损对收益影响较小（${(whatIf.data.stop_loss.delta * 100).toFixed(1)}%），可作为辅助风控手段`}
                    </div>
                  </div>
                </div>
              )}

              {/* Factor Contribution Analysis */}
              <div>
                <h2 className="text-sm font-medium mb-3">因子贡献分析</h2>
                <p className="text-xs mb-3" style={{ color: "var(--text-secondary)" }}>
                  展示每种行为模式对总盈亏的金额贡献。此分析反映持仓组合的盈亏构成，并非反事实回测。
                </p>
                {whatIf.data.items.map((item: any) => (
                  <div
                    key={item.removed_pattern}
                    style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }}
                    className="p-4 mb-3"
                  >
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-medium">{patternLabel(item.removed_pattern)}</span>
                      <span className="text-sm" style={{ color: item.absolute_impact >= 0 ? "var(--success)" : "var(--danger)" }}>
                        金额贡献: {item.absolute_impact >= 0 ? "+" : ""}{item.absolute_impact.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs" style={{ color: "var(--text-secondary)" }}>
                      <span>占比: {(item.contribution_pct * 100).toFixed(0)}%</span>
                      <span>原始收益: {(item.original_return * 100).toFixed(1)}%</span>
                      <span>剔除后: {(item.what_if_return * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            !whatIf.isLoading && !whatIf.error && (
              <div className="text-center py-8" style={{ color: "var(--text-secondary)" }}>
                暂无回测数据
              </div>
            )
          )}
        </>
      )}
    </div>
  );
}
