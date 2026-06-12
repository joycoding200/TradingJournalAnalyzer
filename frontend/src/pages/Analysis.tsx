import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useStats, useInsight, useWhatIf, useRunAnalysis, useGenerateReport } from "../hooks/useAnalysis";
import StatsCards from "../components/StatsCards";
import PatternChart from "../components/PatternChart";
import WhatIfChart from "../components/WhatIfChart";
import { patternLabel } from "../constants/patterns";

type Tab = "stats" | "insight" | "whatif";

export default function Analysis() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>("stats");

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
              <div>
                <h2 className="text-sm font-medium mb-3">各行为模式统计</h2>
                <div style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }} className="overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        <th className="p-3 text-left">行为</th>
                        <th className="p-3 text-right">次数</th>
                        <th className="p-3 text-right">胜率</th>
                        <th className="p-3 text-right">总盈亏</th>
                        <th className="p-3 text-right">均收益率</th>
                      </tr>
                    </thead>
                    <tbody>
                      {insight.data.patterns?.map((p: any) => (
                        <tr key={p.pattern_name} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td className="p-3 font-medium">{patternLabel(p.pattern_name)}</td>
                          <td className="p-3 text-right">{p.count}</td>
                          <td className="p-3 text-right" style={{ color: p.win_rate >= 0.5 ? "var(--success)" : "var(--danger)" }}>
                            {(p.win_rate * 100).toFixed(1)}%
                          </td>
                          <td className="p-3 text-right" style={{ color: p.total_pnl >= 0 ? "var(--success)" : "var(--danger)" }}>
                            {p.total_pnl >= 0 ? "+" : ""}{p.total_pnl.toFixed(2)}
                          </td>
                          <td className="p-3 text-right" style={{ color: p.avg_pnl_pct >= 0 ? "var(--success)" : "var(--danger)" }}>
                            {(p.avg_pnl_pct * 100).toFixed(2)}%
                          </td>
                        </tr>
                      ))}
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
            <div className="space-y-4">
              <h2 className="text-sm font-medium">删除特定行为后的收益变化</h2>
              {whatIf.data.items.map((item: any) => (
                <div
                  key={item.removed_pattern}
                  style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }}
                  className="p-4"
                >
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-medium">{patternLabel(item.removed_pattern)}</span>
                    <span className="text-sm" style={{ color: item.delta > 0.01 ? "var(--success)" : "var(--text-secondary)" }}>
                      影响指数: {(item.contribution_pct * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-6 bg-muted rounded relative overflow-hidden" style={{ backgroundColor: "var(--bg-tertiary)" }}>
                    <div
                      className="absolute left-0 top-0 h-full rounded"
                      style={{
                        width: `${Math.min(Math.abs(item.original_return) * 200, 95)}%`,
                        backgroundColor: "var(--accent)",
                        opacity: 0.5,
                      }}
                    />
                    <div
                      className="absolute left-0 top-0 h-full rounded"
                      style={{
                        width: `${Math.min(Math.abs(item.what_if_return) * 200, 95)}%`,
                        backgroundColor: item.delta > 0.01 ? "var(--success)" : "var(--accent)",
                        opacity: 0.8,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                    <span>原始: {(item.original_return * 100).toFixed(1)}%</span>
                    <span>删除后: {(item.what_if_return * 100).toFixed(1)}%</span>
                    <span style={{ color: "var(--success)" }}>Δ {(item.delta * 100).toFixed(1)}%</span>
                  </div>
                </div>
              ))}
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
