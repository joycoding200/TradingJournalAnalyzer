import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { patternLabel } from "../constants/patterns";

interface PatternData {
  pattern_name: string;
  count: number;
  win_count: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl_pct: number;
}

interface PatternChartProps {
  data: PatternData[];
}

export default function PatternChart({ data }: PatternChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="py-8 text-center text-text-secondary">
        暂无行为标签数据
      </div>
    );
  }

  const chartData = data.map((d) => ({
    name: patternLabel(d.pattern_name),
    winRate: +(d.win_rate * 100).toFixed(1),
    count: d.count,
    isPositive: d.total_pnl > 0,
  }));

  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-4">
      <h3 className="mb-4 text-sm font-medium text-text-secondary">
        各行为标签胜率
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="name" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
          <YAxis unit="%" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
          <Tooltip
            formatter={(value) => `${Number(value)}%`}
            contentStyle={{
              backgroundColor: "var(--bg-tertiary)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              color: "var(--text-primary)",
            }}
          />
          <Bar dataKey="winRate" name="胜率" radius={[4, 4, 0, 0]}>
            {chartData.map((d, i) => (
              <Cell key={i} fill={d.isPositive ? "#22c55e" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
