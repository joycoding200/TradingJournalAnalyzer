import { useState } from "react";
import { Collapsible } from "./ui";
import KpiCard from "./KpiCard";
import EquityCurve from "./EquityCurve";
import SymbolSummaryTable from "./SymbolSummaryTable";
import { formatMoney } from "../utils/format";

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
  max_win_symbol?: string;
  max_win_date?: string;
  max_loss_symbol?: string;
  max_loss_date?: string;
  consecutive_losses?: number;
  avg_win_amount?: number;
  avg_loss_amount?: number;
  win_loss_ratio?: number;
  profit_factor?: number;
  max_drawdown?: number;
  avg_mae?: number;
  avg_mfe?: number;
  profit_capture_ratio?: number;
  expectancy?: number;
  max_drawdown_pct?: number;
  total_return_pct?: number;
  avg_win_pct?: number;
  avg_loss_pct?: number;
  equity_curve?: Array<{ date: string; cum_pnl: number; cum_pnl_pct: number }>;
  symbol_summary?: Array<{ symbol: string; symbol_name?: string; trade_count: number; win_count: number; win_rate: number; total_pnl: number; avg_holding_days: number; first_trade_date: string; last_trade_date: string }>;
}

interface StatsCardsProps {
  stats: StatsData;
  /**
   * When provided, the unknown-cost banner's "add earlier statement"
   * button calls this handler instead of navigating to /upload. This
   * opens the in-page AddFileModal — the same path as the "+ 添加交割单"
   * button in the Analysis header — so the user stays on the analysis
   * page and React Query invalidation refreshes the data automatically.
   */
  onAddFile?: () => void;
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

interface Rating {
  text: string;
  color: string;
}

/** Large hero-style card for the 4 core metrics. */
function heroCard(
  cls: string,
  label: string,
  value: string,
  summary: string,
  rating?: Rating
) {
  return <KpiCard key={label} cls={cls} label={label} value={value} summary={summary} rating={rating} variant="hero" />;
}

/** Compact card for detailed metrics section. */
function detailCard(
  cls: string,
  label: string,
  value: string,
  hint?: string,
  rating?: Rating,
  summary?: string,
) {
  return <KpiCard key={label} cls={cls} label={label} value={value} hint={hint} rating={rating} summary={summary} variant="detail" />;
}

export default function StatsCards({ stats, onAddFile }: StatsCardsProps) {
  const unknown = stats.unknown_cost_count ?? 0;
  const [bannerOpen, setBannerOpen] = useState(false);
  const wlr = stats.win_loss_ratio ?? 0;
  const pf = stats.profit_factor ?? 0;
  const expectancy = stats.expectancy ?? 0;
  const mae = stats.avg_mae ?? 0;
  const mfe = stats.avg_mfe ?? 0;
  const capture = stats.profit_capture_ratio ?? 0;
  const noLoss = (stats.loss_count ?? 0) === 0 && (stats.win_count ?? 0) > 0;
  const ddPct = stats.max_drawdown_pct ?? 0;

  // ── 人话总结（P1）─────────────────────────────────────────────
  const pnlSummary = (stats.total_pnl ?? 0) >= 0
    ? `每笔交易平均赚 ${formatMoney((stats.total_pnl ?? 0) / Math.max(stats.total_positions ?? 1, 1))}，你的交易整体是赚钱的`
    : `扣除手续费后整体亏损，需要找出亏损来源并纠正`;

  const wrSummary = (stats.win_rate ?? 0) >= 0.5
    ? "超过一半的交易在赚钱，选股或择时能力不错"
    : "多数交易在赔钱，需要重点关注入场时机";

  const ddSummary = ddPct > 0.3
    ? `回撤很大——你的账户一度亏掉 ${formatPct(ddPct)}，这说明扛了不该扛的亏损`
    : ddPct > 0.15
    ? "回撤偏高，建议控制单笔亏损来降低波动"
    : "回撤控制得很好，亏的时候砍得快";

  // ── Core 4 hero cards ─────────────────────────────────────────
  const totalPositions = stats.total_positions ?? 0;
  const winCount = stats.win_count ?? 0;
  const lossCount = stats.loss_count ?? 0;
  const closedCount = winCount + lossCount; // 已平仓 = 赚钱 + 亏钱
  const totalTrades = stats.total_trades ?? 0; // 总成交笔数

  const heroes = [
    heroCard(
      (stats.total_pnl ?? 0) >= 0 ? "success" : "danger",
      "总盈亏",
      formatMoney(stats.total_pnl ?? 0),
      pnlSummary,
      { text: (stats.total_pnl ?? 0) >= 0 ? "✓ 整体盈利" : "✗ 整体亏损", color: (stats.total_pnl ?? 0) >= 0 ? "success" : "danger" }
    ),
    heroCard(
      (stats.win_rate ?? 0) >= 0.5 ? "success" : "danger",
      "胜率",
      formatPct(stats.win_rate ?? 0),
      `${winCount} 笔赚钱 / ${closedCount} 笔已平仓 — ${wrSummary}`,
    ),
    heroCard(
      ddPct > 0.2 ? "danger" : ddPct > 0.1 ? "accent" : "success",
      "最大回撤",
      formatPct(ddPct),
      ddSummary,
    ),
    heroCard(
      "primary",
      "已平仓",
      `${closedCount} 笔`,
      `总成交 ${totalTrades} 笔｜完整建仓 ${totalPositions} 笔｜已平仓 ${closedCount} 笔（${winCount} 赚 / ${lossCount} 亏）`,
    ),
  ];

  // ── Detail cards (was tier2 + some tier1, now collapsed) ─────
  const pfRating: Rating = noLoss ? { text: "无亏损", color: "success" }
    : pf >= 3 ? { text: "优秀", color: "success" }
    : pf >= 1.5 ? { text: "良好", color: "success" }
    : pf >= 1 ? { text: "合格", color: "accent" }
    : { text: "不合格", color: "danger" };

  const exRating: Rating = expectancy > 0.02 ? { text: "优秀", color: "success" }
    : expectancy > 0 ? { text: "正期望", color: "success" }
    : { text: "负期望", color: "danger" };

  const maeRating: Rating = mae < -0.1 ? { text: "风险较高", color: "danger" }
    : mae < -0.05 ? { text: "风险可控", color: "accent" }
    : { text: "回撤较小", color: "success" };

  const captureRating: Rating = capture >= 0.5 ? { text: "优秀", color: "success" }
    : capture >= 0.3 ? { text: "良好", color: "success" }
    : capture >= 0.15 ? { text: "一般", color: "accent" }
    : { text: "较差：存在过早卖出", color: "danger" };

  const detailCards: ReturnType<typeof detailCard>[] = [
    // Basic stats
    detailCard("success", "单笔最大盈利", formatMoney(stats.max_win ?? 0),
      stats.max_win_symbol ? `${stats.max_win_symbol} ${stats.max_win_date}` : undefined,
      undefined,
      stats.max_win && stats.max_win > 0 ? "你最好的一笔交易，想想当时做对了什么" : undefined),
    detailCard("danger", "单笔最大亏损", noLoss ? "--" : formatMoney(stats.max_loss ?? 0),
      noLoss ? "无亏损记录" : (stats.max_loss_symbol ? `${stats.max_loss_symbol} ${stats.max_loss_date}` : undefined),
      undefined,
      stats.max_loss && stats.max_loss < 0 ? "这笔亏损贡献了最大回撤的大部分，值得复盘" : undefined),
    detailCard("primary", "平均持仓", `${(stats.avg_holding_days ?? 0).toFixed(1)}天`,
      `盈利${(stats.avg_win_holding_days ?? 0).toFixed(0)}天 / 亏损${(stats.avg_loss_holding_days ?? 0).toFixed(0)}天`,
      undefined,
      (stats.avg_loss_holding_days ?? 0) > (stats.avg_win_holding_days ?? 0) * 2
        ? "亏钱的持仓时间远长于赚钱的——典型的'截断利润，让亏损奔跑'" : undefined),

    // Financial ratios
    detailCard("primary", "平均盈利", formatMoney(stats.avg_win_amount ?? 0),
      `平均 ${formatPct(stats.avg_win_pct ?? 0)} / 笔`,
      undefined,
      (stats.avg_win_pct ?? 0) > 0.1 ? "盈利能力不错，单笔赚 10% 以上" : "单笔盈利偏薄，可以考虑让利润跑一跑"),
    detailCard("danger", "平均亏损", noLoss ? "无亏损记录" : formatMoney(stats.avg_loss_amount ?? 0),
      noLoss ? undefined : `平均 ${formatPct(stats.avg_loss_pct ?? 0)} / 笔`,
      undefined,
      (stats.avg_loss_pct ?? 0) < -0.08
        ? "平均亏损超过 8%，需要设止损来限亏" : "平均亏损控制在可接受范围"),

    // PF — key metric
    detailCard(noLoss ? "success" : (pf >= 1.5 ? "success" : pf >= 1 ? "accent" : "danger"),
      "盈亏比（赚的钱 ÷ 亏的钱）", noLoss ? "∞" : pf.toFixed(2),
      ">1.0 合格, >1.5 良好, >3.0 优秀", pfRating,
      pf < 1 ? "赚的不够亏的多，问题出在要么胜率太低要么亏的太快" : pf < 1.5
        ? "勉强盈利，还有改善空间" : "盈亏结构健康"),
  ];

  // ── Advanced metrics (collapsed) ──────────────────────────────
  const advancedCards: ReturnType<typeof detailCard>[] = [
    detailCard(expectancy >= 0 ? "success" : "danger",
      "预期收益（Expectancy）", formatPct(expectancy),
      "每笔交易平均预期盈亏", exRating,
      expectancy > 0.02 ? "长期来看你的策略有正期望，坚持执行就能赚钱"
        : expectancy > 0 ? "微弱的正期望，需要提高胜率或盈亏比"
        : "策略长期必亏，必须调整"),
    detailCard("primary", "损益比（Payoff Ratio）", noLoss ? "∞" : wlr.toFixed(2),
      "平均盈利 ÷ 平均亏损",
      undefined,
      wlr >= 2 ? "赚的时候赚得多，亏的时候亏得少，很健康" : wlr >= 1
        ? "盈亏金额基本持平" : "亏的时候比赚的时候金额大"),

    detailCard(mae < -0.08 ? "danger" : "primary",
      "最大浮亏容忍（MAE）", formatPct(mae),
      "持仓期间平均最大浮亏", maeRating,
      mae < -0.08 ? "你经常扛到浮亏很深才止损，这是亏损的主要来源" : undefined),
    detailCard("primary",
      "最大浮盈（MFE）", formatPct(mfe),
      "持仓期间平均最高浮盈",
      undefined,
      mfe > 0.05 ? "持仓期间经常能赚到 5% 以上，说明选股方向对" : undefined),
    detailCard(capture >= 0.3 ? "success" : capture >= 0.15 ? "accent" : "danger",
      "止盈效率", formatPct(capture),
      "最终盈利 ÷ 最大浮盈，越高越能拿住利润", captureRating,
      capture < 0.2 ? "经常在赚钱的时候过早离场，浮盈变实盈的比例太低" : undefined),
    detailCard((stats.consecutive_losses ?? 0) > 3 ? "danger" : "primary",
      "连续亏损", `${stats.consecutive_losses ?? 0}次`,
      "最长连续亏损次数",
      undefined,
      (stats.consecutive_losses ?? 0) > 5
        ? "连亏超过 5 次，情绪容易崩——建议设一个'连亏休息日'规则" : undefined),
  ];

  return (
    <div>
      {unknown > 0 && (
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 text-sm text-warning">
          <button
            type="button"
            onClick={() => setBannerOpen(!bannerOpen)}
            aria-expanded={bannerOpen}
            className="flex w-full cursor-pointer items-center justify-between border-0 bg-transparent px-3 py-2 text-left text-warning focus-ring"
          >
            <span className="flex items-center gap-2">
              <span aria-hidden>⚠</span>
              <span>
                {unknown} 笔持仓起始于交割单外，盈亏已标记为 0
              </span>
            </span>
            <span className="text-xs opacity-70">
              {bannerOpen ? "收起" : "详情"}
            </span>
          </button>
          {bannerOpen && (
            <div className="px-3 pb-3">
              <p className="mb-2 text-warning/90">
                如需更准确的结果，可补传更早期的交割单。
              </p>
              {onAddFile && (
                <button
                  type="button"
                  onClick={onAddFile}
                  className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-warning/40 bg-warning/10 px-2.5 py-1 text-xs font-medium text-warning transition-colors hover:bg-warning/20 focus-ring"
                >
                  一键添加更早的交割单 →
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* V4.0: 净值曲线图 */}
      <EquityCurve data={stats.equity_curve || []} />

      {/* ── Core 4 hero cards ─────────────────────────────── */}
      <div className="mb-2 text-xs font-medium text-text-secondary">核心概览</div>
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">{heroes}</div>

      {/* V4.0: 股票维度盈亏 */}
      <div className="mb-2 text-xs font-medium text-text-secondary">股票维度盈亏</div>
      <div className="mb-6 rounded-lg border border-border bg-bg-tertiary/30 p-4">
        <SymbolSummaryTable data={stats.symbol_summary || []} />
      </div>

      {/* ── Detailed metrics (collapsed) ──────────────────── */}
      <Collapsible title="展开详细数据（盈亏比、单笔明细、持仓分析）">
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3">{detailCards}</div>

        {/* ── Advanced (deeply collapsed) ─── */}
        <Collapsible title="展开高级指标（预期收益、MAE/MFE、止盈效率）">
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3">{advancedCards}</div>
        </Collapsible>
      </Collapsible>
    </div>
  );
}
