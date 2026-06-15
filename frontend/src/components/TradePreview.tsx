interface Trade {
  [key: string]: unknown;
}

interface TradePreviewProps {
  trades: Trade[];
  onImport: () => void;
  loading?: boolean;
}

const COLUMNS = ["编号", "股票代码", "方向", "数量", "价格", "手续费", "时间"];

export default function TradePreview({ trades, onImport, loading }: TradePreviewProps) {
  const display = trades.slice(0, 100);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
          共解析 {trades.length} 条交易记录{trades.length > 100 ? "（仅显示前 100 条）" : ""}
        </span>
        <button
          onClick={onImport}
          disabled={loading}
          style={{
            backgroundColor: "var(--accent)",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            padding: "10px 24px",
            cursor: "pointer",
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? "导入中..." : "确认导入"}
        </button>
      </div>
      <div style={{ overflowX: "auto", borderRadius: "8px", border: "1px solid var(--border)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
          <thead>
            <tr style={{ backgroundColor: "var(--bg-tertiary)" }}>
              {COLUMNS.map((col) => (
                <th
                  key={col}
                  style={{
                    padding: "8px 12px",
                    textAlign: "left",
                    borderBottom: "1px solid var(--border)",
                    color: "var(--text-secondary)",
                    fontWeight: 500,
                    whiteSpace: "nowrap",
                  }}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {display.map((trade, i) => (
              <tr
                key={i}
                style={{
                  borderBottom: "1px solid var(--border)",
                  backgroundColor: i % 2 === 0 ? "transparent" : "var(--bg-secondary)",
                }}
              >
                {COLUMNS.map((col) => (
                  <td
                    key={col}
                    style={{
                      padding: "6px 12px",
                      whiteSpace: "nowrap",
                      color: "var(--text-primary)",
                    }}
                  >
                    {String(trade[col] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
