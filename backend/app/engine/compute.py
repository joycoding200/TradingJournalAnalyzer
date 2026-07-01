"""Unified computation engine for TradeDoctor analysis pipeline.

Computes stats, insight, and what-if in a single pass and returns complete
Pydantic response objects. Called at analysis creation time (runAnalysis) and
file linking time (linkFiles). Results are stored as JSONB snapshots in the
Analysis table so GET endpoints return instantly.

Key optimizations vs. the old per-endpoint approach:
- Trades loaded once, positions built once
- Market data fetched in parallel (ThreadPoolExecutor)
- Pattern tagging runs once and shared across insight + whatif
- Shapley values computed once and cached
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from app.api.common import get_raw_file_ids, get_raw_file_filenames, build_symbol_name_map
from app.engine.attribution import shapley_attribution
from app.engine.insight import InsightEngine, InsightItem
from app.engine.mae import compute_mae_mfe_stats
from app.engine.market_fetcher import ensure_market_data
from app.engine.pattern import PatternEngine
from app.engine.position import PositionBuilder
from app.engine.whatif import ProfitAttribution
from app.models.analysis import Analysis
from app.schemas.analysis import (
    AttributionItem,
    CrossAnalysisItem,
    EquityPoint,
    InsightPatternItem,
    InsightResponse,
    PnlLevelItem,
    PositionItem,
    RuleSimulationItem,
    ShapleyItem,
    StatsResponse,
    SymbolSummaryItem,
    WhatIfResponse,
)

logger = logging.getLogger(__name__)


# ─── Shared computation helpers ──────────────────────────────────────────────

def _compute_consecutive_losses(positions) -> int:
    streak = 0
    max_streak = 0
    for p in positions:
        if p.pnl <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


def _module_for_pattern(pattern_name: str) -> str:
    """Pattern → dimension. Delegates to PatternEngine.CATEGORY_MAP (single source)."""
    return PatternEngine.CATEGORY_MAP.get(pattern_name, "behavior")


def persist_snapshot(db: Session, analysis, field: str, payload) -> None:
    """Self-heal: write one snapshot field on the Analysis row + commit.

    Used by the three GET slow paths (get_stats/get_insight/get_whatif) so the
    next request hits the fast path. Mirrors the pattern run_analysis already
    uses. Rolls back on commit failure so a poisoned session doesn't break the
    response (the in-memory payload is still returned to the caller).
    """
    setattr(analysis, field, payload)
    try:
        db.commit()
    except Exception:
        logger.exception("failed to cache %s for analysis %s", field, analysis.id)
        db.rollback()


def _select_best_worst_patterns(all_items: list):
    """Pick the best (max total_pnl) and worst (min total_pnl) significant
    patterns. "Significant" = count >= 5.

    The previous code took ``significant[0]`` and ``significant[-1]`` on the
    flat ``all_items`` list, but that list is built by extending items from
    multiple pattern dimensions in insertion order — it is NOT sorted across
    dimensions. So ``significant[-1]`` could land on a positive-contribution
    pattern, mislabelling it as "最大问题" in the diagnostic conclusion.

    Fix: sort by total_pnl and pick the explicit max / min.
    - best  = significant item with the largest  total_pnl (most positive)
    - worst = significant item with the smallest total_pnl (most negative)
    When fewer than two significant items exist, worst is None (best may still
    be set with a single significant item). See 缺陷2.
    """
    significant = [p for p in all_items if p.count >= 5]
    if not significant:
        return None, None
    significant_sorted = sorted(significant, key=lambda p: p.total_pnl, reverse=True)
    best = significant_sorted[0]
    worst = significant_sorted[-1] if len(significant_sorted) > 1 else None
    return best, worst


def _build_category_map(
    positions, trades=None, market_data=None, precomputed=None
) -> dict[int, dict[str, str]]:
    """Tag each position and return {index: {category: pattern_name}}.

    If ``precomputed`` (a {index: list[PatternResult]} of already-tagged,
    hierarchy-resolved results including psychology) is supplied, skip the
    tagging/psychology work and only run ``resolve_per_category``. This lets
    callers that already computed the PatternResult list (e.g. report.py,
    which builds patterns_map for WhatIf) reuse it instead of re-tagging the
    whole position set a second time. Output is identical to the non-precomputed
    path on the same inputs (see test_build_category_map_precomputed_matches).
    """
    if precomputed is not None:
        category_map: dict[int, dict[str, str]] = {}
        for i in range(len(positions)):
            results = precomputed.get(i, [])
            resolved = PatternEngine.resolve_per_category(results)
            category_map[i] = {
                r.category: r.pattern_name for r in resolved if r.category
            }
        return category_map

    tag_kwargs = {}
    if trades:
        tag_kwargs["trades"] = trades
        tag_kwargs["all_trades"] = trades

    psychology_results = PatternEngine.detect_psychological_patterns(
        positions, all_trades=trades or None
    )
    psyche_by_pos: dict[int, list] = {}
    for idx, psy_result in psychology_results:
        psyche_by_pos.setdefault(idx, []).append(psy_result)

    category_map = {}
    for i, pos in enumerate(positions):
        results = PatternEngine.tag_position(pos, positions, **tag_kwargs)
        if market_data:
            results.extend(PatternEngine.tag_market_patterns(pos, market_data))
        results = PatternEngine.resolve_hierarchy(results)
        if i in psyche_by_pos:
            results.extend(psyche_by_pos[i])
        resolved = PatternEngine.resolve_per_category(results)
        category_map[i] = {r.category: r.pattern_name for r in resolved if r.category}
    return category_map


# ─── Lazy market-data fetch helper ───────────────────────────────────────────

def ensure_market_data_parallel(
    db: Session,
    symbols: list[str],
    date_start,
    date_end,
    max_workers: int = 4,
) -> None:
    """Fetch market data for all symbols in parallel using a thread pool.

    Falls back to sequential if ThreadPoolExecutor fails (e.g. in dev with
    limited thread support).
    """
    if not symbols:
        return

    def _fetch_one(sym: str) -> None:
        ensure_market_data(db, [sym], date_start, date_end)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    future.result()
                except Exception:
                    logger.warning("market_data_parallel: failed for %s", sym, exc_info=True)
    except Exception:
        # Fallback: sequential
        logger.info("ThreadPoolExecutor unavailable, falling back to sequential fetch")
        for sym in symbols:
            try:
                _fetch_one(sym)
            except Exception:
                logger.warning("market_data_sequential: failed for %s", sym, exc_info=True)


# ─── Stats computation ───────────────────────────────────────────────────────

def compute_stats(
    analysis: Analysis,
    trades: list,
    db: Session,
) -> StatsResponse:
    """Compute all stats KPI data. Mirrors the original get_stats logic."""
    file_ids = get_raw_file_ids(analysis.id, db)
    filename_map = get_raw_file_filenames(file_ids, db)
    filenames = [filename_map.get(fid, "") for fid in file_ids]
    analysis_filename = filenames[0] if filenames else ""

    positions = PositionBuilder.build(trades)

    # Build symbol -> Chinese-name lookup (shared with get_stats slow path).
    symbol_name_map = build_symbol_name_map(trades)

    total_trades = len(trades)
    total_positions = len(positions)
    unknown_cost_count = sum(1 for p in positions if not getattr(p, "cost_known", True))

    valid_positions = [p for p in positions if getattr(p, "cost_known", True)]
    valid_count = len(valid_positions)
    is_small_sample = valid_count < 5

    win_count = sum(1 for p in valid_positions if p.pnl > 0)
    win_rate = (win_count / valid_count) if valid_count > 0 else 0.0
    total_pnl = sum(p.pnl for p in valid_positions)
    avg_holding_days = (
        sum(p.holding_days for p in valid_positions) / valid_count
        if valid_count > 0 else 0.0
    )
    max_win_pos = max(valid_positions, key=lambda p: p.pnl, default=None)
    max_loss_pos = min(valid_positions, key=lambda p: p.pnl, default=None)
    max_win = max_win_pos.pnl if max_win_pos else 0.0
    max_loss = max_loss_pos.pnl if max_loss_pos else 0.0
    max_win_symbol = max_win_pos.symbol if max_win_pos else ""
    max_win_date = str(max_win_pos.exit_date) if max_win_pos else ""
    max_loss_symbol = max_loss_pos.symbol if max_loss_pos else ""
    max_loss_date = str(max_loss_pos.exit_date) if max_loss_pos else ""
    consecutive_losses = _compute_consecutive_losses(
        sorted(valid_positions, key=lambda p: p.exit_date)
    )

    # PnL level distribution
    pnl_counts: dict[str, int] = {}
    for p in valid_positions:
        level_info = PatternEngine.classify_pnl_level(p)
        level = level_info["level"]
        if level:
            pnl_counts[level] = pnl_counts.get(level, 0) + 1
    pnl_distribution = [
        PnlLevelItem(level=level, count=count)
        for level, count in sorted(pnl_counts.items())
    ]

    # Symbol summary
    symbol_summary_data: list[dict] = []
    symbol_groups: dict[str, list] = {}
    for p in valid_positions:
        symbol_groups.setdefault(p.symbol, []).append(p)
    for symbol, group in symbol_groups.items():
        win_pos = [p for p in group if p.pnl > 0]
        sym_trade_count = len(group)
        sym_win_count = len(win_pos)
        total_pnl_sym = sum(p.pnl for p in group)
        avg_hold = sum(p.holding_days for p in group) / sym_trade_count if sym_trade_count > 0 else 0.0
        exit_dates = [p.exit_date for p in group]
        symbol_summary_data.append({
            "symbol": symbol,
            "symbol_name": symbol_name_map.get(symbol),
            "trade_count": sym_trade_count,
            "win_count": sym_win_count,
            "win_rate": round(sym_win_count / sym_trade_count, 4) if sym_trade_count > 0 else 0.0,
            "total_pnl": round(total_pnl_sym, 2),
            "avg_holding_days": round(avg_hold, 1),
            "first_trade_date": str(min(exit_dates)) if exit_dates else "",
            "last_trade_date": str(max(exit_dates)) if exit_dates else "",
        })
    symbol_summary_data.sort(key=lambda x: x["total_pnl"], reverse=True)

    position_items = [
        PositionItem(
            symbol=p.symbol,
            asset_type=p.asset_type,
            entry_date=p.entry_date,
            exit_date=p.exit_date,
            holding_days=p.holding_days,
            total_quantity=p.total_quantity,
            avg_entry_price=p.avg_entry_price,
            avg_exit_price=p.avg_exit_price,
            pnl=p.pnl,
            pnl_pct=p.pnl_pct,
            trade_ids=p.trade_ids,
            entry_count=getattr(p, "entry_count", 0),
            total_buys=getattr(p, "total_buys", 0.0),
            total_sells=getattr(p, "total_sells", 0.0),
        )
        for p in positions
    ]

    # Financial metrics
    win_positions = [p for p in valid_positions if p.pnl > 0]
    loss_positions = [p for p in valid_positions if p.pnl <= 0]
    loss_count = len(loss_positions)

    avg_win_amount = sum(p.pnl for p in win_positions) / len(win_positions) if win_positions else 0.0
    avg_loss_amount = sum(p.pnl for p in loss_positions) / len(loss_positions) if loss_positions else 0.0
    avg_win_pct = sum(p.pnl_pct for p in win_positions) / len(win_positions) if win_positions else 0.0
    avg_loss_pct = sum(p.pnl_pct for p in loss_positions) / len(loss_positions) if loss_positions else 0.0
    win_loss_ratio = avg_win_amount / abs(avg_loss_amount) if avg_loss_amount != 0 else None
    total_gross_profit = sum(p.pnl for p in win_positions)
    total_gross_loss = abs(sum(p.pnl for p in loss_positions))
    profit_factor = total_gross_profit / total_gross_loss if total_gross_loss > 0 else None

    avg_win_holding = sum(p.holding_days for p in win_positions) / len(win_positions) if win_positions else 0.0
    avg_loss_holding = sum(p.holding_days for p in loss_positions) / len(loss_positions) if loss_positions else 0.0

    total_invested = sum(p.avg_entry_price * p.total_quantity for p in valid_positions)
    total_return_pct = total_pnl / total_invested if total_invested > 0 else 0.0

    # Max drawdown + equity curve
    sorted_positions = sorted(valid_positions, key=lambda p: p.exit_date)
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    equity_curve_data: list[dict] = []
    if sorted_positions:
        equity_curve_data.append({
            "date": str(sorted_positions[0].exit_date),
            "cum_pnl": 0.0,
            "cum_pnl_pct": 0.0,
        })
    for p in sorted_positions:
        cum_pnl += p.pnl
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd
        equity_curve_data.append({
            "date": str(p.exit_date),
            "cum_pnl": round(cum_pnl, 2),
            "cum_pnl_pct": round(cum_pnl / total_invested, 4) if total_invested > 0 else 0.0,
        })
    # Drawdown % denominator = peak account equity (principal + peak floating
    # profit), NOT peak floating profit alone. See analysis.py:get_stats for
    # the full rationale (P0b: trough crossing zero must not yield >100%).
    dd_denom = (total_invested + peak) if (total_invested + peak) > 0 else 0.0
    max_drawdown_pct = (max_dd / dd_denom) if dd_denom > 0 else 0.0

    # Expectancy
    total_expectancy = 0.0
    if valid_count > 0:
        total_expectancy = InsightItem.compute(valid_positions)

    return StatsResponse(
        filename=analysis_filename,
        filenames=filenames,
        raw_file_ids=file_ids,
        total_trades=total_trades,
        total_positions=total_positions,
        unknown_cost_count=unknown_cost_count,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=round(win_rate, 2),
        total_pnl=round(total_pnl, 2),
        avg_holding_days=round(avg_holding_days, 1),
        avg_win_holding_days=round(avg_win_holding, 1),
        avg_loss_holding_days=round(avg_loss_holding, 1),
        max_win=round(max_win, 2),
        max_loss=round(max_loss, 2),
        max_win_symbol=max_win_symbol,
        max_win_date=max_win_date,
        max_loss_symbol=max_loss_symbol,
        max_loss_date=max_loss_date,
        consecutive_losses=consecutive_losses,
        profit_factor=round(profit_factor, 2) if profit_factor is not None else None,
        avg_win_amount=round(avg_win_amount, 2),
        avg_loss_amount=round(avg_loss_amount, 2),
        win_loss_ratio=round(win_loss_ratio, 2) if win_loss_ratio is not None else None,
        max_drawdown=round(max_dd, 2),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        total_return_pct=round(total_return_pct, 4),
        avg_win_pct=round(avg_win_pct, 4),
        avg_loss_pct=round(avg_loss_pct, 4),
        pnl_distribution=pnl_distribution,
        positions=position_items,
        avg_mae=0.0,
        avg_mfe=0.0,
        mae_winners=0.0,
        mae_losers=0.0,
        profit_capture_ratio=0.0,
        expectancy=round(total_expectancy, 2),
        is_small_sample=is_small_sample,
        equity_curve=[EquityPoint(**pt) for pt in equity_curve_data],
        symbol_summary=[SymbolSummaryItem(**s) for s in symbol_summary_data],
    )


# ─── Insight computation ─────────────────────────────────────────────────────

def compute_insight(
    positions: list,
    trades: list,
    category_map: dict[int, dict[str, str]],
) -> InsightResponse:
    """Compute pattern insight from already-built positions and category map."""
    items_by_cat = InsightEngine.analyze_by_category(positions, category_map)

    def to_pattern_item(i) -> InsightPatternItem:
        return InsightPatternItem(
            pattern_name=i.pattern_name,
            count=i.count,
            win_count=i.win_count,
            win_rate=round(i.win_rate, 4),
            total_pnl=i.total_pnl,
            avg_pnl_pct=round(i.avg_pnl_pct, 4),
            expectancy=round(i.expectancy, 4),
            gross_profit=round(getattr(i, "gross_profit", 0.0), 2),
            gross_loss=round(getattr(i, "gross_loss", 0.0), 2),
        )

    all_items = []
    cat_items: dict[str, list[InsightPatternItem]] = {}
    for cat, cat_insight_items in items_by_cat.items():
        converted = [to_pattern_item(i) for i in cat_insight_items]
        cat_items[cat] = converted
        all_items.extend(converted)

    market_env_items = [p for p in all_items if _module_for_pattern(p.pattern_name) == "market_env"]
    behavior_items = [p for p in all_items if _module_for_pattern(p.pattern_name) == "behavior"]
    outcome_items = [p for p in all_items if _module_for_pattern(p.pattern_name) == "outcome"]
    psychology_items = [p for p in all_items if _module_for_pattern(p.pattern_name) == "psychology"]

    valid_positions = [p for i, p in enumerate(positions) if getattr(p, "cost_known", True)]
    valid_indices = {i for i, p in enumerate(positions) if getattr(p, "cost_known", True)}
    baseline_expectancy = InsightItem.compute(valid_positions) if valid_positions else 0.0

    best, worst = _select_best_worst_patterns(all_items)

    # Cross-dimension analysis
    cross_data: dict[tuple[str, str], dict] = {}
    for i in valid_indices:
        cat = category_map.get(i, {})
        env = cat.get("market_env", "SIDEWAYS")
        beh = cat.get("behavior", "未标记")
        key = (env, beh)
        p = positions[i]
        if key not in cross_data:
            cross_data[key] = {"count": 0, "win_count": 0, "total_pnl": 0.0, "total_pnl_pct": 0.0}
        cross_data[key]["count"] += 1
        if p.pnl > 0:
            cross_data[key]["win_count"] += 1
        cross_data[key]["total_pnl"] += p.pnl
        cross_data[key]["total_pnl_pct"] += p.pnl_pct
    cross_analysis = [
        CrossAnalysisItem(
            market_env=env,
            behavior=beh,
            count=d["count"],
            win_count=d["win_count"],
            win_rate=round(d["win_count"] / d["count"], 4) if d["count"] > 0 else 0.0,
            total_pnl=round(d["total_pnl"], 2),
            avg_pnl_pct=round(d["total_pnl_pct"] / d["count"], 4) if d["count"] > 0 else 0.0,
        )
        for (env, beh), d in sorted(cross_data.items(), key=lambda kv: kv[1]["total_pnl"], reverse=True)
    ]

    return InsightResponse(
        patterns=all_items,
        market_env=market_env_items,
        behavior=behavior_items,
        outcome=outcome_items,
        psychology=psychology_items,
        entry_patterns=market_env_items,
        holding_patterns=behavior_items,
        risk_patterns=outcome_items,
        exit_patterns=psychology_items,
        categories=cat_items,
        best_pattern=best,
        worst_pattern=worst,
        baseline_expectancy=round(baseline_expectancy, 4),
        cross_analysis=cross_analysis,
    )


# ─── WhatIf computation ──────────────────────────────────────────────────────

def compute_whatif(
    positions: list,
    category_map: dict[int, dict[str, str]],
    market_data: dict,
) -> WhatIfResponse:
    """Compute what-if analysis from already-built positions and category map."""
    valid_positions = [p for p in positions if getattr(p, "cost_known", True)]

    # Build pattern names per position
    patterns_map_names: dict[int, list[str]] = {}
    for idx, cats in category_map.items():
        names = list(cats.values())
        if names:
            patterns_map_names[idx] = names

    items = ProfitAttribution.attribution_analysis(positions, patterns_map_names)
    whatif_items = [
        AttributionItem(
            removed_pattern=i.removed_pattern,
            original_return=i.original_return,
            what_if_return=i.what_if_return,
            delta=i.delta,
            contribution_pct=i.contribution_pct,
            absolute_impact=i.absolute_impact,
        )
        for i in items
    ]

    # ── 规则回测模拟（V1.2.3: 5个规则全算，固定标准档参数）────────────
    # 必须与 api/analysis.py 的 get_whatif 慢路径保持一致（PROJECT_EXPERIENCE:
    # compute_stats vs get_stats 两处各写一份需同步，compute_whatif 同理）。
    # delta = 模拟后收益率 − 现状收益率，delta>0 = 该规则改善收益
    def _run_rule(rt, params):
        result = ProfitAttribution.analyze_rule(
            valid_positions, rule_type=rt, params=params, market_data=market_data
        )
        if not result:
            return None
        return RuleSimulationItem(
            rule=result["rule"],
            original_return=result["original_return"],
            what_if_return=result["what_if_return"],
            delta=result["delta"],
            affected_positions=result["affected_positions"],
        )

    # 止损侧：固定8%止损（标准档，原5%偏紧）+ 仅大亏止损
    stop_loss_sim = _run_rule("stop_loss", {"loss_pct": 0.08})
    stop_loss_large_loss_sim = _run_rule(
        "stop_loss_large_loss", {"loss_pct": 0.08, "large_loss_pct": -0.08}
    )
    # 移动止损：跟踪 high 回撤 8%
    trailing_stop_sim = _run_rule("trailing_stop", {"trail_pct": 0.08})
    # 止盈侧：固定止盈 +10% + 移动止盈(模式A) 5%/5%
    take_profit_sim = _run_rule("take_profit", {"profit_pct": 0.10})
    trailing_take_profit_sim = _run_rule(
        "trailing_take_profit", {"activation_pct": 0.05, "trail_pct": 0.05}
    )

    # Shapley attribution
    shapley_values = shapley_attribution(positions, patterns_map_names)
    total_pnl = sum(p.pnl for p in valid_positions)
    # Denom is abs(total_pnl) so the percentage's SIGN follows shapley_value:
    # a profit-contributing pattern (val>0) shows a positive pct even when the
    # account is net negative. Dividing by a negative total_pnl flipped signs
    # (e.g. +3999 on a -8475 account rendered as "-47.2%"), misleading users into
    # thinking profitable patterns lost money.
    denom = abs(total_pnl)
    shapley_items = [
        ShapleyItem(
            pattern_name=pat,
            shapley_value=val,
            pct_of_total=round(val / denom * 100, 1) if denom > 0 else 0.0,
        )
        for pat, val in sorted(shapley_values.items(), key=lambda x: -x[1])
    ]

    return WhatIfResponse(
        items=whatif_items,
        stop_loss=stop_loss_sim,
        stop_loss_large_loss=stop_loss_large_loss_sim,
        trailing_stop=trailing_stop_sim,
        take_profit=take_profit_sim,
        trailing_take_profit=trailing_take_profit_sim,
        shapley=shapley_items,
    )


# ─── Unified pipeline ────────────────────────────────────────────────────────

def compute_all(
    analysis: Analysis,
    trades: list,
    db: Session,
) -> tuple[StatsResponse, InsightResponse, WhatIfResponse]:
    """Run the full analysis pipeline: positions → stats → insight → whatif.

    Caller must load trades before calling. Returns all three response objects.
    Results should be stored as snapshots and committed by the caller.
    """
    if not trades:
        # Edge case: no trades yet (e.g. file was empty). Return empty responses.
        from datetime import date
        empty_stats = StatsResponse(
            filename="",
            filenames=[],
            raw_file_ids=[],
            total_trades=0,
            total_positions=0,
            unknown_cost_count=0,
            win_count=0,
            loss_count=0,
            win_rate=0.0,
            total_pnl=0.0,
            avg_holding_days=0.0,
            avg_win_holding_days=0.0,
            avg_loss_holding_days=0.0,
            max_win=0.0, max_loss=0.0,
            max_win_symbol="", max_win_date="",
            max_loss_symbol="", max_loss_date="",
            consecutive_losses=0,
            profit_factor=None,
            avg_win_amount=0.0, avg_loss_amount=0.0,
            win_loss_ratio=None,
            max_drawdown=0.0, max_drawdown_pct=0.0,
            total_return_pct=0.0,
            avg_win_pct=0.0, avg_loss_pct=0.0,
            pnl_distribution=[],
            positions=[],
            avg_mae=0.0, avg_mfe=0.0,
            mae_winners=0.0, mae_losers=0.0,
            profit_capture_ratio=0.0,
            expectancy=0.0,
            is_small_sample=True,
            equity_curve=[],
            symbol_summary=[],
        )
        empty_insight = InsightResponse(
            patterns=[], market_env=[], behavior=[], outcome=[], psychology=[],
            entry_patterns=[], holding_patterns=[], risk_patterns=[], exit_patterns=[],
            categories={}, best_pattern=None, worst_pattern=None,
            baseline_expectancy=0.0, cross_analysis=[],
        )
        empty_whatif = WhatIfResponse(items=[], stop_loss=None, shapley=[])
        return empty_stats, empty_insight, empty_whatif

    # Build positions
    positions = PositionBuilder.build(trades)

    # Fetch market data in parallel
    symbols: list[str] = list({p.symbol for p in positions})
    if symbols:
        ensure_market_data_parallel(db, symbols, analysis.date_start, analysis.date_end)

    # Compute stats
    stats = compute_stats(analysis, trades, db)

    # Load market data for pattern tagging (needed by insight + whatif)
    market_data: dict[str, Any] = {}
    if symbols:
        from app.engine.market_data import MarketDataCache
        market_data = MarketDataCache.get_market_data(db, symbols, analysis.date_start, analysis.date_end)

    # Build category map (shared by insight + whatif)
    category_map = _build_category_map(positions, trades=trades, market_data=market_data)

    # Compute MAE/MFE and patch into stats
    if symbols:
        mae_mfe_stats_result = compute_mae_mfe_stats(
            [p for p in positions if getattr(p, "cost_known", True)],
            market_data,
        )
        stats.avg_mae = round(mae_mfe_stats_result.get("avg_mae", 0.0), 4)
        stats.avg_mfe = round(mae_mfe_stats_result.get("avg_mfe", 0.0), 4)
        stats.mae_winners = round(mae_mfe_stats_result.get("mae_winners", 0.0), 4)
        stats.mae_losers = round(mae_mfe_stats_result.get("mae_losers", 0.0), 4)
        stats.profit_capture_ratio = round(mae_mfe_stats_result.get("profit_capture_ratio", 0.0), 4)

    # Compute insight
    insight = compute_insight(positions, trades, category_map)

    # Compute whatif
    whatif = compute_whatif(positions, category_map, market_data)

    return stats, insight, whatif
