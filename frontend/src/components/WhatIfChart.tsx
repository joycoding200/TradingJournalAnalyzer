import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

interface WhatIfData {
  label: string;
  original_return: number;
  whatif_return: number;
}

interface WhatIfChartProps {
  data: WhatIfData[];
}

export default function WhatIfChart({ data }: WhatIfChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="text-center py-8" style={{ color: "var(--text-secondary)" }}>
        暂无回测数据
      </div>
    );
  }

  return (
    <div style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }} className="p-4">
      <h3 className="text-sm font-medium mb-4" style={{ color: "var(--text-secondary)" }}>
        情景回测对比
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
          <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--bg-tertiary)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              color: "var(--text-primary)",
            }}
          />
          <Legend wrapperStyle={{ color: "var(--text-secondary)" }} />
          <Bar dataKey="original_return" name="原始收益" fill="var(--accent)" radius={[4, 4, 0, 0]} />
          <Bar dataKey="whatif_return" name="删除后收益" fill="var(--warning)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
