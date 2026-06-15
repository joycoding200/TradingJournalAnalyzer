"""Analysis API routes: run analysis, fetch stats / insight / what-if."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.analysis import Analysis
from app.models.trade import Trade
from app.models.user import User
from app.engine.insight import InsightEngine
from app.engine.market_fetcher import ensure_market_data
from app.engine.pattern import PatternEngine
from app.engine.position import PositionBuilder
from app.engine.whatif import ProfitAttribution
from app.schemas.analysis import (
    AnalysisRunRequest,
    AnalysisRunResponse,
    AttributionItem,
    InsightPatternItem,
    InsightResponse,
    OutcomeItem,
    PositionItem,
    RuleSimulationItem,
    StatsResponse,
    WhatIfResponse,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# Pattern module mapping (synchronized with pattern_definition.yaml)
PATTERN_MODULES: dict[str, str] = {
    "CHASE": "entry",
    "BOTTOM": "entry",
    "BREAKOUT": "entry",
    "TREND": "entry",
    "COUNTER_TREND": "entry",
    "BREAKDOWN": "entry",
    "SCALP": "holding",
    "SWING": "holding",
    "POSITION": "holding",
    "PYRAMID": "risk",
    "AVERAGE_DOWN": "risk",
    "TURN": "risk",
    "TIGHT_STOP": "exit",
    "TRAILING_STOP": "exit",
    "TIME_EXIT": "exit",
    "LARGE_LOSS_EXIT": "exit",
    "FOMO": "entry",
}


@router.post(
    "/run",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_analysis(
    body: AnalysisRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an analysis record for the given date range."""
    analysis = Analysis(
        user_id=current_user.id,
        date_start=body.date_start,
        date_end=body.date_end,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return AnalysisRunResponse(analysis_id=analysis.id)


def _load_analysis(analysis_id: str, user_id: str, db: Session) -> Analysis:
    """Load analysis, raise 404 if not found or not owned by user."""
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.user_id == user_id)
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


def _load_trades(
    analysis: Analysis, user_id: str, db: Session
) -> list[Trade]:
    """Load trades within the analysis date range."""
    start_dt = datetime.combine(analysis.date_start, datetime.min.time())
    end_dt = datetime.combine(analysis.date_end, datetime.max.time())
    return (
        db.query(Trade)
        .filter(
            Trade.user_id == user_id,
            Trade.datetime >= start_dt,
            Trade.datetime <= end_dt,
        )
        .order_by(Trade.datetime)
        .all()
    )


def _compute_consecutive_losses(positions) -> int:
    """Count the longest consecutive losing streak from positions."""
    streak = 0
    max_streak = 0
    for p in positions:
        if p.pnl < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return max_streak


@router.get("/{analysis_id}/stats", response_model=StatsResponse)
def get_stats(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compute KPI stats and positions for the analysis."""
    analysis = _load_analysis(analysis_id, current_user.id, db)
    trades = _load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)

    total_trades = len(trades)
    total_positions = len(positions)
    unknown_cost_count = sum(1 for p in positions if not getattr(p, "cost_known", True))

    # Use only valid positions (cost_known == True) for all KPIs
    valid_positions = [p for p in positions if getattr(p, "cost_known", True)]
    valid_count = len(valid_positions)

    win_count = sum(1 for p in valid_positions if p.pnl > 0)
    win_rate = (win_count / valid_count) if valid_count > 0 else 0.0
    total_pnl = sum(p.pnl for p in valid_positions)
    avg_holding_days = (
        sum(p.holding_days for p in valid_positions) / valid_count
        if valid_count > 0
        else 0.0
    )
    max_win = max((p.pnl for p in valid_positions), default=0.0)
    max_loss = min((p.pnl for p in valid_positions), default=0.0)
    consecutive_losses = _compute_consecutive_losses(valid_positions)

    # Outcome distribution
    outcome_counts: dict[str, int] = {}
    for p in valid_positions:
        outcome = PatternEngine.compute_outcome(p)
        label = outcome["label"]
        if label:
            outcome_counts[label] = outcome_counts.get(label, 0) + 1
    outcome_distribution = [
        OutcomeItem(label=label, count=count)
        for label, count in sorted(outcome_counts.items())
    ]

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
        )
        for p in positions
    ]

    # New financial metrics
    win_positions = [p for p in valid_positions if p.pnl > 0]
    loss_positions = [p for p in valid_positions if p.pnl <= 0]
    loss_count = len(loss_positions)

    avg_win_amount = sum(p.pnl for p in win_positions) / len(win_positions) if win_positions else 0.0
    avg_loss_amount = sum(p.pnl for p in loss_positions) / len(loss_positions) if loss_positions else 0.0
    win_loss_ratio = avg_win_amount / abs(avg_loss_amount) if avg_loss_amount != 0 else 0.0

    total_gross_profit = sum(p.pnl for p in win_positions)
    total_gross_loss = abs(sum(p.pnl for p in loss_positions))
    profit_factor = total_gross_profit / total_gross_loss if total_gross_loss > 0 else 0.0

    avg_win_holding = sum(p.holding_days for p in win_positions) / len(win_positions) if win_positions else 0.0
    avg_loss_holding = sum(p.holding_days for p in loss_positions) / len(loss_positions) if loss_positions else 0.0

    # Max drawdown: cumulative PnL peak-to-trough
    sorted_positions = sorted(valid_positions, key=lambda p: p.exit_date)
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in sorted_positions:
        cum_pnl += p.pnl
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd

    # --- Outcome distribution ---

    # --- Position items ---

    # --- Return ---
    return StatsResponse(
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
        consecutive_losses=consecutive_losses,
        profit_factor=round(profit_factor, 2),
        avg_win_amount=round(avg_win_amount, 2),
        avg_loss_amount=round(avg_loss_amount, 2),
        win_loss_ratio=round(win_loss_ratio, 2),
        max_drawdown=round(max_dd, 2),
        outcome_distribution=outcome_distribution,
        positions=position_items,
    )


def _build_category_map(
    positions, trades=None, market_data=None
) -> dict[int, dict[str, str]]:
    """Tag each position and return {index: {category: pattern_name}}.

    Merges Module 1 (entry, requires market_data), Module 2 (holding),
    Module 3 (risk/exit) tags. One tag per category per position.
    """
    tag_kwargs = {}
    if trades:
        tag_kwargs["trades"] = trades
        tag_kwargs["all_trades"] = trades

    category_map: dict[int, dict[str, str]] = {}
    for i, pos in enumerate(positions):
        results = PatternEngine.tag_position(pos, positions, **tag_kwargs)
        if market_data:
            results.extend(
                PatternEngine.tag_market_patterns(pos, market_data)
            )
            results = PatternEngine.resolve_hierarchy(results)
        resolved = PatternEngine.resolve_per_category(results)
        category_map[i] = {r.category: r.pattern_name for r in resolved if r.category}
    return category_map


def _module_for_pattern(pattern_name: str) -> str:
    """Return the module name for a pattern (entry/holding/risk)."""
    return PATTERN_MODULES.get(pattern_name, "risk")


@router.get("/{analysis_id}/insight", response_model=InsightResponse)
def get_insight(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the full pipeline and return pattern analysis."""
    analysis = _load_analysis(analysis_id, current_user.id, db)
    trades = _load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)

    # Fetch market data for entry-pattern tagging (CHASE/BOTTOM/BREAKOUT/TREND etc.)
    symbols = list({p.symbol for p in positions})
    market_data = {}
    if symbols:
        date_start = analysis.date_start
        date_end = analysis.date_end
        market_data = ensure_market_data(db, symbols, date_start, date_end)

    category_map = _build_category_map(positions, trades=trades, market_data=market_data)
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
        )

    # Flat list + per-category lists
    all_items = []
    cat_items: dict[str, list[InsightPatternItem]] = {}
    for cat, cat_insight_items in items_by_cat.items():
        converted = [to_pattern_item(i) for i in cat_insight_items]
        cat_items[cat] = converted
        all_items.extend(converted)

    # Group by module for backward compat
    entry_patterns = [p for p in all_items if _module_for_pattern(p.pattern_name) == "entry"]
    holding_patterns = [p for p in all_items if _module_for_pattern(p.pattern_name) == "holding"]
    risk_patterns = [p for p in all_items if _module_for_pattern(p.pattern_name) == "risk"]
    exit_patterns = [p for p in all_items if _module_for_pattern(p.pattern_name) == "exit"]

    significant = [p for p in all_items if p.count >= 5]
    best = significant[0] if significant else None
    worst = significant[-1] if len(significant) > 1 else None

    return InsightResponse(
        patterns=all_items,
        entry_patterns=entry_patterns,
        holding_patterns=holding_patterns,
        risk_patterns=risk_patterns,
        exit_patterns=exit_patterns,
        categories=cat_items,
        best_pattern=best,
        worst_pattern=worst,
    )


@router.get("/{analysis_id}/whatif", response_model=WhatIfResponse)
def get_whatif(
    analysis_id: str,
    rule_type: str = "stop_loss",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run what-if analysis: factor contribution + stop-loss rule simulation."""
    analysis = _load_analysis(analysis_id, current_user.id, db)
    trades = _load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)
    valid_positions = [p for p in positions if getattr(p, "cost_known", True)]

    # Fetch market data for entry-pattern tagging
    symbols = list({p.symbol for p in positions})
    market_data = {}
    if symbols:
        date_start = analysis.date_start
        date_end = analysis.date_end
        market_data = ensure_market_data(db, symbols, date_start, date_end)

    category_map = _build_category_map(positions, trades=trades, market_data=market_data)
    # Use all available category patterns per position for behavioral what-if
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

    # Stop-loss rule simulation (correct denominator-invariant method)
    stop_loss_sim = None
    if rule_type == "stop_loss":
        result = ProfitAttribution.analyze_rule(
            valid_positions,
            rule_type="stop_loss",
            params={"loss_pct": 0.05},
        )
        if result:
            stop_loss_sim = RuleSimulationItem(
                rule=result["rule"],
                original_return=result["original_return"],
                what_if_return=result["what_if_return"],
                delta=result["delta"],
                affected_positions=result["affected_positions"],
            )

    return WhatIfResponse(items=whatif_items, stop_loss=stop_loss_sim)
