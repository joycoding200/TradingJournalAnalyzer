import { Collapsible } from "./ui";
import { patternLabel } from "../constants/patterns";

interface ShapleyItem {
  pattern_name: string;
  shapley_value: number;
  pct_of_total: string;
}

export function ShapleyPanel({ data }: { data: ShapleyItem[] }) {
  if (!data || data.length === 0) return null;

  return (
    <Collapsible title="赚钱来源分析（公平归因，点击展开）">
      <p className="mb-3 text-xs text-text-secondary">
        各标签对总收益的贡献占比，总和=100%，消除重复计算。
      </p>
      {data.map((s) => (
        <div key={s.pattern_name} className="mb-2">
          <div className="mb-1 flex justify-between text-xs">
            <span>{patternLabel(s.pattern_name)}</span>
            <span className={s.shapley_value >= 0 ? "text-success" : "text-danger"}>
              {s.shapley_value >= 0 ? "+" : ""}{s.shapley_value.toFixed(2)}（{s.pct_of_total}%）
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded bg-border">
            <div
              className={[
                "h-full rounded transition-[width] duration-300",
                s.shapley_value >= 0 ? "bg-success" : "bg-danger",
              ].join(" ")}
              style={{ width: `${Math.abs(parseFloat(s.pct_of_total))}%` }}
            />
          </div>
        </div>
      ))}
    </Collapsible>
  );
}
