import { patternLabel } from "../constants/patterns";

interface PatternRow {
  pattern_name: string;
  count: number;
  win_rate: number;
  expectancy: number;
  gross_profit?: number;
  gross_loss?: number;
}

export function InsightTable({ patterns, baseline }: { patterns: PatternRow[]; baseline: number }) {
  if (!patterns || patterns.length === 0) {
    return (
      <div className="p-3 text-center text-sm text-text-secondary">
        无数据
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[600px] text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="p-3 text-left">标签</th>
            <th className="p-3 text-right">次数</th>
            <th className="p-3 text-right">胜率</th>
            <th className="p-3 text-right">预期值</th>
            <th className="p-3 text-right">盈亏比(PF)</th>
            <th className="max-w-[160px] p-3 text-left">评价</th>
          </tr>
        </thead>
        <tbody>
          {patterns.map((p) => {
            const isPos = p.expectancy > 0;
            const pf = (p.gross_loss ?? 0) > 0
              ? (p.gross_profit ?? 0) / (p.gross_loss ?? 1)
              : (p.gross_profit ?? 0) > 0 ? Infinity : 0;
            const isSmallSample = p.count < 5;

            let evalText: string;
            let evalColorClass: string;
            if (isSmallSample) {
              evalText = `样本不足（${p.count}笔），暂不评价`;
              evalColorClass = "text-text-secondary";
            } else if (isPos && pf > 2) {
              evalText = "优秀：正期望且显著优于均值，核心盈利模式";
              evalColorClass = "text-success";
            } else if (isPos && p.expectancy > baseline) {
              evalText = "良好：优于均值，建议保持";
              evalColorClass = "text-success";
            } else if (isPos && p.expectancy <= baseline) {
              evalText = "正收益但低于最佳模式，可优化";
              evalColorClass = "text-accent";
            } else {
              evalText = "负期望：持续亏损，建议减少或改进";
              evalColorClass = "text-danger";
            }

            const labelColor = isPos
              ? "text-success"
              : p.expectancy < 0
                ? "text-danger"
                : "text-text-primary";
            const pfColor = pf >= 1.5 ? "text-success" : pf >= 1 ? "text-accent" : "text-danger";

            return (
              <tr
                key={p.pattern_name}
                className={[
                  "border-b border-border transition-colors duration-150",
                  isPos ? "bg-success/[0.04]" : "bg-danger/[0.04]",
                  isSmallSample ? "opacity-60" : "",
                ].join(" ")}
              >
                <td className={`p-3 font-medium ${labelColor}`}>
                  {isSmallSample ? "" : isPos ? "✓ " : "✗ "}{patternLabel(p.pattern_name)}
                </td>
                <td className="p-3 text-right">{p.count}</td>
                <td className={`p-3 text-right ${p.win_rate >= 0.5 ? "text-success" : "text-danger"}`}>
                  {(p.win_rate * 100).toFixed(1)}%
                </td>
                <td className={`p-3 text-right font-semibold ${isPos ? "text-success" : "text-danger"}`}>
                  {p.expectancy >= 0 ? "+" : ""}{(p.expectancy * 100).toFixed(1)}%
                </td>
                <td className={`p-3 text-right ${pfColor}`}>
                  {pf === Infinity ? "∞" : pf.toFixed(2)}
                </td>
                <td className={`max-w-[160px] p-3 text-xs ${evalColorClass}`}>
                  {p.expectancy > baseline && !isSmallSample ? "↑ " : p.expectancy < baseline && !isSmallSample ? "↓ " : ""}{evalText}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
