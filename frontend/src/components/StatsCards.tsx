import { useState } from "react";

interface StatsData {
  total_trades?: number;
  total_positions?: number;
  unknown_cost_count?: number;
  win_count?: number;
  loss_count?: number;
  win_rate?: number;
  total_pnl?: number;
  avg_holding_days?: number;
  avg_win_holding_days?: number;
  avg_loss_holding_days?: number;
  max_win?: number;
  max_loss?: number;
  consecutive_losses?: number;
  avg_win_amount?: number;
  avg_loss_amount?: number;
  win_loss_ratio?: number;
  profit_factor?: number;
  max_drawdown?: number;
  avg_mae?: number;
  avg_mfe?: number;
  mae_winners?: number;
  mae_losers?: number;
  profit_capture_ratio?: number;
  expectancy?: number;
  // V2.5 percentage versions
  max_drawdown_pct?: number;
  total_return_pct?: number;
  avg_win_pct?: number;
  avg_loss_pct?: number;
}

interface StatsCardsProps {
  stats: StatsData;
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatMoney(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

function ratingLabel(value: number, thresholds: [number, string, string][], fallback: string): string {
  for (const [t, label] of thresholds) {
    if (value >= t) return label;
  }
  return fallback;
}

export default function StatsCards({ stats }: StatsCardsProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const unknown = stats.unknown_cost_count ?? 0;

  function card(cls: string, label: string, value: string, hint?: string, rating?: { text: string; color: string }) {
    return (
      <div key={label} style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }} className="p-4">
        <div className="text-xs mb-1" style={{ color: "var(--text-secondary)" }}>{label}</div>
        <div className="text-xl font-semibold" style={{ color: cls }}>{value}</div>
        {rating && <div className="text-xs mt-1 font-medium" style={{ color: rating.color }}>{rating.text}</div>}
        {hint && <div className="text-xs mt-0.5" style={{ color: "var(--text-secondary)", opacity: 0.7 }}>{hint}</div>}
      </div>
    );
  }

  const wlr = stats.win_loss_ratio ?? 0;
  const pf = stats.profit_factor ?? 0;
  const expectancy = stats.expectancy ?? 0;
  const mae = stats.avg_mae ?? 0;
  const mfe = stats.avg_mfe ?? 0;
  const capture = stats.profit_capture_ratio ?? 0;

  // ---- Tier 1: 核心结果 ---------------------------------
  const tier1 = [
    card((stats.total_pnl ?? 0) >= 0 ? "var(--success)" : "var(--danger)", "总盈亏", formatMoney(stats.total_pnl ?? 0),
      `收益率 ${formatPct(stats.total_return_pct ?? 0)}`,
      { text: (stats.total_pnl ?? 0) >= 0 ? "✓ 整体盈利" : "✗ 整体亏损", color: (stats.total_pnl ?? 0) >= 0 ? "var(--success)" : "var(--danger)" }),
    card((stats.win_rate ?? 0) >= 0.5 ? "var(--success)" : "var(--danger)", "胜率", formatPct(stats.win_rate ?? 0),
      "盈利笔数 ÷ 总笔数"),
    card((stats.max_drawdown_pct ?? 0) > 0.2 ? "var(--danger)" : (stats.max_drawdown_pct ?? 0) > 0.1 ? "var(--accent)" : "var(--success)", "最大回撤", formatPct(stats.max_drawdown_pct ?? 0),
      `最大回撤金额 ${formatMoney(stats.max_drawdown ?? 0)}`),
    card("var(--success)", "单笔最大盈利", formatMoney(stats.max_win ?? 0),
      stats.max_win_symbol ? `${stats.max_win_symbol} ${stats.max_win_date}` : undefined),
    card("var(--danger)", "单笔最大亏损", formatMoney(stats.max_loss ?? 0),
      stats.max_loss_symbol ? `${stats.max_loss_symbol} ${stats.max_loss_date}` : undefined),
    card("var(--text-primary)", "完整交易", `${stats.total_positions ?? 0}`,
      `${stats.win_count ?? 0}盈 / ${stats.loss_count ?? 0}亏`),
  ];

  // ---- Tier 2: 进阶分析 ---------------------------------
  const pfRating = pf >= 3 ? { text: "优秀（>3.0）", color: "var(--success)" }
    : pf >= 1.5 ? { text: "良好（>1.5）", color: "var(--success)" }
    : pf >= 1 ? { text: "合格（>1.0）", color: "var(--accent)" }
    : { text: "不合格（<1.0）", color: "var(--danger)" };

  const exRating = expectancy > 0.02 ? { text: "优秀", color: "var(--success)" }
    : expectancy > 0 ? { text: "正期望", color: "var(--success)" }
    : { text: "负期望", color: "var(--danger)" };

  const tier2 = [
    card(pf >= 1.5 ? "var(--success)" : pf >= 1 ? "var(--accent)" : "var(--danger)",
      "盈亏比（Profit Factor）", pf.toFixed(2),
      "总盈利 ÷ 总亏损，>1.5为合格", pfRating),
    card(expectancy >= 0 ? "var(--success)" : "var(--danger)",
      "预期收益（Expectancy）", formatPct(expectancy),
      "每笔交易预期赚多少", exRating),
    card("var(--text-primary)", "损益比（Payoff Ratio）", wlr.toFixed(2),
      "平均盈利 ÷ 平均亏损"),
    card("var(--text-primary)", "平均持仓", `${(stats.avg_holding_days ?? 0).toFixed(1)}天`,
      `盈利${(stats.avg_win_holding_days ?? 0).toFixed(0)}天 / 亏损${(stats.avg_loss_holding_days ?? 0).toFixed(0)}天`),
    card("var(--success)", "平均盈利", formatMoney(stats.avg_win_amount ?? 0),
      `平均 ${formatPct(stats.avg_win_pct ?? 0)} / 笔`),
    card("var(--danger)", "平均亏损", formatMoney(stats.avg_loss_amount ?? 0),
      `平均 ${formatPct(stats.avg_loss_pct ?? 0)} / 笔`),
  ];

  // ---- Tier 3: 专业指标 ---------------------------------
  const maeRating = mae < -0.1 ? { text: "风险较高", color: "var(--danger)" }
    : mae < -0.05 ? { text: "风险可控", color: "var(--accent)" }
    : { text: "回撤较小", color: "var(--success)" };

  const captureRating = capture >= 0.5 ? { text: "优秀", color: "var(--success)" }
    : capture >= 0.3 ? { text: "良好", color: "var(--success)" }
    : capture >= 0.15 ? { text: "一般", color: "var(--accent)" }
    : { text: "较差：存在过早卖出", color: "var(--danger)" };

  const tier3 = [
    card(mae < -0.08 ? "var(--danger)" : "var(--text-primary)",
      "最大回撤容忍度（MAE）", formatPct(mae),
      "持仓期间平均最大浮亏", maeRating),
    card("var(--text-primary)",
      "最大浮盈（MFE）", formatPct(mfe),
      "持仓期间平均最高盈利"),
    card(capture >= 0.3 ? "var(--success)" : capture >= 0.15 ? "var(--accent)" : "var(--danger)",
      "止盈效率（Profit Capture）", formatPct(capture),
      "最终盈利 ÷ 最大浮盈，衡量兑现能力", captureRating),
    card((stats.consecutive_losses ?? 0) > 3 ? "var(--danger)" : "var(--text-primary)",
      "连续亏损", `${stats.consecutive_losses ?? 0}次`,
      "最长连续亏损次数"),
  ];

  return (
    <div>
      {unknown > 0 && (
        <div className="mb-4 p-3 rounded-lg text-sm" style={{ backgroundColor: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.3)", color: "#eab308" }}>
          ⚠ 检测到 {unknown} 笔卖出对应的买入发生在交割单起始日期之前，持仓成本未知，已标记为盈亏=0。建议导入更早期的交割单以获得完整分析。
        </div>
      )}

      {/* Tier 1: 核心结果 */}
      <div className="mb-2 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>核心结果</div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">{tier1}</div>

      {/* Tier 2: 进阶分析 */}
      <div className="mb-2 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>进阶分析</div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">{tier2}</div>

      {/* Tier 3: 专业指标 — collapsible */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        style={{
          backgroundColor: "transparent", border: "none", cursor: "pointer",
          color: "var(--text-secondary)", fontSize: "12px", fontWeight: 500,
          padding: 0, marginBottom: showAdvanced ? 8 : 0,
        }}
      >
        {showAdvanced ? "▾ 收起高级分析" : "▸ 展开高级分析（MAE/MFE/止盈效率）"}
      </button>
      {showAdvanced && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">{tier3}</div>
      )}
    </div>
  );
}
