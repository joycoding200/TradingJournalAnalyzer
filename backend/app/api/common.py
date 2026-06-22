"""Common functions shared between API modules."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.trade import Trade


def load_analysis(analysis_id: str, user_id: str, db: Session) -> Analysis:
    """Load analysis, raise 404 if not found or not owned by user."""
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.user_id == user_id)
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


def load_trades(analysis: Analysis, user_id: str, db: Session) -> list[Trade]:
    """Load the trades that belong to THIS analysis.

    An analysis is bound to exactly one uploaded raw file (Upload flow always
    passes raw_file_id). Loading by user_id + date range instead is wrong: if a
    user re-uploads an already-imported statement (or uploads several whose
    dates overlap), the overlapping trades get double-counted and silently
    corrupt PnL/win-rate. So the analysis's data boundary is its raw_file_id,
    not the user's entire history within a date window.
    """
    if not analysis.raw_file_id:
        # Defensive: an analysis without a raw file has no trades to analyze.
        return []
    return (
        db.query(Trade)
        .filter(
            Trade.raw_file_id == analysis.raw_file_id,
            Trade.user_id == user_id,
            Trade.is_deleted.is_(False),
        )
        .order_by(Trade.datetime)
        .all()
    )
