import { useState } from "react";

interface SymbolSummaryItem {
  symbol: string;
  trade_count: number;
  win_count: number;
  win_rate: number;
  total_pnl: number;
  avg_holding_days: number;
  first_trade_date: string;
  last_trade_date: string;
}

interface SymbolSummaryTableProps {
  data: SymbolSummaryItem[];
}

type SortKey = "symbol" | "trade_count" | "win_rate" | "total_pnl" | "avg_holding_days";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "symbol", label: "股票代码" },
  { key: "trade_count", label: "交易次数" },
  { key: "win_rate", label: "胜率" },
  { key: "total_pnl", label: "总盈亏" },
  { key: "avg_holding_days", label: "平均持仓天数" },
];

function formatMoney(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function SymbolSummaryTable({ data }: SymbolSummaryTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("total_pnl");
  const [sortAsc, setSortAsc] = useState(false);

  if (!data || data.length === 0) {
    return (
      <div className="rounded-lg py-6 text-center text-sm text-text-secondary">
        暂无交易数据
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => {
    const aVal = a[sortKey];
    const bVal = b[sortKey];
    const dir = sortAsc ? 1 : -1;
    if (typeof aVal === "number" && typeof bVal === "number") {
      return (aVal - bVal) * dir;
    }
    return String(aVal).localeCompare(String(bVal)) * dir;
  });

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(key !== "total_pnl"); // default desc for PnL, asc for others
    }
  };

  const sortIndicator = (key: SortKey) => {
    if (key !== sortKey) return "";
    return sortAsc ? " ↑" : " ↓";
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={() => handleSort(col.key)}
                className="cursor-pointer select-none whitespace-nowrap px-3 py-2 text-left text-xs font-medium text-text-secondary hover:text-text-primary"
              >
                {col.label}
                <span className="opacity-50">{sortIndicator(col.key)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((item) => (
            <tr
              key={item.symbol}
              className="border-b border-border transition-[filter] hover:brightness-110"
            >
              <td className="px-3 py-2 font-medium text-text-primary">
                {item.symbol}
              </td>
              <td className="px-3 py-2 text-text-secondary">
                {item.trade_count}
              </td>
              <td className="px-3 py-2 text-text-secondary">
                {formatPct(item.win_rate)}
              </td>
              <td
                className={[
                  "px-3 py-2 font-medium",
                  item.total_pnl > 0
                    ? "text-success"
                    : item.total_pnl < 0
                      ? "text-danger"
                      : "text-text-secondary",
                ].join(" ")}
              >
                {formatMoney(item.total_pnl)}
              </td>
              <td className="px-3 py-2 text-text-secondary">
                {item.avg_holding_days.toFixed(1)}天
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
