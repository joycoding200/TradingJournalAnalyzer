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
from app.engine.pattern import PatternEngine
from app.engine.position import PositionBuilder
from app.engine.whatif import WhatIfEngine
from app.schemas.analysis import (
    AnalysisRunRequest,
    AnalysisRunResponse,
    InsightPatternItem,
    InsightResponse,
    PositionItem,
    StatsResponse,
    WhatIfItem,
    WhatIfResponse,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


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
    win_count = sum(1 for p in positions if p.pnl > 0)
    win_rate = (win_count / total_positions) if total_positions > 0 else 0.0
    total_pnl = sum(p.pnl for p in positions)
    avg_holding_days = (
        sum(p.holding_days for p in positions) / total_positions
        if total_positions > 0
        else 0.0
    )
    max_win = max((p.pnl for p in positions), default=0.0)
    max_loss = min((p.pnl for p in positions), default=0.0)
    consecutive_losses = _compute_consecutive_losses(positions)

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

    return StatsResponse(
        total_trades=total_trades,
        total_positions=total_positions,
        win_count=win_count,
        win_rate=round(win_rate, 2),
        total_pnl=round(total_pnl, 2),
        avg_holding_days=round(avg_holding_days, 1),
        max_win=round(max_win, 2),
        max_loss=round(max_loss, 2),
        consecutive_losses=consecutive_losses,
        positions=position_items,
    )


def _build_patterns_map(positions):
    """Tag each position and return {index: [pattern_name, ...]}."""
    patterns_map: dict[int, list[str]] = {}
    for i, pos in enumerate(positions):
        results = PatternEngine.tag_position(pos, positions)
        patterns_map[i] = [r.pattern_name for r in results]
    return patterns_map


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
    patterns_map = _build_patterns_map(positions)
    items = InsightEngine.analyze(positions, patterns_map)

    pattern_items = [
        InsightPatternItem(
            pattern_name=i.pattern_name,
            count=i.count,
            win_count=i.win_count,
            win_rate=round(i.win_rate, 4),
            total_pnl=i.total_pnl,
            avg_pnl_pct=round(i.avg_pnl_pct, 4),
        )
        for i in items
    ]

    best = pattern_items[0] if pattern_items else None
    worst = pattern_items[-1] if len(pattern_items) > 1 else None

    return InsightResponse(
        patterns=pattern_items,
        best_pattern=best,
        worst_pattern=worst,
    )


@router.get("/{analysis_id}/whatif", response_model=WhatIfResponse)
def get_whatif(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the full pipeline and return what-if results."""
    analysis = _load_analysis(analysis_id, current_user.id, db)
    trades = _load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)
    patterns_map = _build_patterns_map(positions)
    items = WhatIfEngine.analyze(positions, patterns_map)

    whatif_items = [
        WhatIfItem(
            removed_pattern=i.removed_pattern,
            original_return=i.original_return,
            what_if_return=i.what_if_return,
            delta=i.delta,
            damage_score=i.damage_score,
        )
        for i in items
    ]

    return WhatIfResponse(items=whatif_items)
