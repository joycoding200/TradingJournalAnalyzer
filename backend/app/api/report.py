"""Report API routes: generate AI report, fetch report(s)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.prompt import SYSTEM_PROMPT, build_user_prompt
from app.ai.provider import get_llm
from app.ai.validator import ReportValidator, generate_with_retry
from app.auth.jwt import get_current_user
from app.config import settings
from app.database import get_db
from app.models.analysis import Analysis
from app.models.report import Report
from app.models.trade import Trade
from app.models.user import User
from app.engine.insight import InsightEngine
from app.engine.pattern import PatternEngine
from app.engine.position import PositionBuilder
from app.engine.whatif import ProfitAttribution
from app.schemas.report import (
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportListItem,
    ReportResponse,
    ReportsListResponse,
)

router = APIRouter(prefix="/api", tags=["report"])


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


def _load_trades(analysis: Analysis, user_id: str, db: Session) -> list:
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


def _build_analysis_data(trades, positions, insight_items, whatif_items) -> dict:
    """Build the analysis_data dict expected by build_user_prompt."""
    total_trades = len(trades)
    total_positions = len(positions)
    win_count = sum(1 for p in positions if p.pnl > 0)
    win_rate = (win_count / total_positions * 100) if total_positions > 0 else 0.0
    total_pnl = sum(p.pnl for p in positions)
    avg_holding_days = (
        sum(p.holding_days for p in positions) / total_positions
        if total_positions > 0
        else 0.0
    )

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_holding_days": round(avg_holding_days, 1),
        "patterns": [
            {
                "pattern_name": i.pattern_name,
                "count": i.count,
                "win_rate": i.win_rate,
                "total_pnl": i.total_pnl,
            }
            for i in insight_items
        ],
        "what_if": [
            {
                "removed_pattern": i.removed_pattern,
                "delta": i.delta,
                "contribution_pct": i.contribution_pct,
            }
            for i in whatif_items
        ],
    }


@router.post(
    "/report/generate",
    response_model=ReportGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_report(
    body: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run full pipeline, build AI prompt, call LLM, validate, save report."""
    analysis = _load_analysis(body.analysis_id, current_user.id, db)
    trades = _load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)

    # Build patterns map with confidence scores
    patterns_map: dict[int, list[tuple[str, float]]] = {}
    for i, pos in enumerate(positions):
        results = PatternEngine.tag_position(pos, positions)
        patterns_map[i] = [(r.pattern_name, r.confidence) for r in results]

    # Resolve primary pattern per position for insight PnL attribution
    primary_map = InsightEngine._resolve_primary(patterns_map)
    patterns_map_flat: dict[int, list[str]] = {
        i: [p] for i, p in primary_map.items()
    }

    # Run insight and what-if engines
    insight_items = InsightEngine.analyze(positions, patterns_map_flat)
    # WhatIf uses all patterns (not just primary)
    patterns_map_names: dict[int, list[str]] = {
        i: [name for name, _ in pats] for i, pats in patterns_map.items()
    }
    whatif_items = ProfitAttribution.attribution_analysis(positions, patterns_map_names)

    # Build AI prompt
    analysis_data = _build_analysis_data(trades, positions, insight_items, whatif_items)
    user_prompt = build_user_prompt(analysis_data)

    # Call LLM
    provider = get_llm()
    report_content = await generate_with_retry(
        provider, SYSTEM_PROMPT, user_prompt, analysis_data
    )

    # Validate
    validation = ReportValidator().validate(report_content, analysis_data)

    # Save
    report = Report(
        user_id=current_user.id,
        analysis_id=body.analysis_id,
        analysis_input=analysis_data,
        ai_provider=settings.ai_provider,
        report_content=report_content,
        validation_passed=validation.is_valid,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return ReportGenerateResponse(report_id=report.id, status="generated")


@router.get("/report/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a stored report by id."""
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return ReportResponse(
        id=report.id,
        analysis_id=report.analysis_id,
        analysis_input=report.analysis_input,
        ai_provider=report.ai_provider,
        report_content=report.report_content,
        validation_passed=report.validation_passed,
        created_at=report.created_at,
    )


@router.get("/reports", response_model=ReportsListResponse)
def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's most recent reports (last 50), with source filenames."""
    from app.models.analysis import Analysis
    from app.models.raw_file import RawFile

    reports = (
        db.query(Report)
        .filter(Report.user_id == current_user.id)
        .order_by(Report.created_at.desc())
        .limit(50)
        .all()
    )

    analysis_ids = [r.analysis_id for r in reports if r.analysis_id]
    filename_map: dict[str, str] = {}
    if analysis_ids:
        analyses = db.query(Analysis).filter(Analysis.id.in_(analysis_ids)).all()
        raw_file_ids = [a.raw_file_id for a in analyses if a.raw_file_id]
        filename_by_raw = {}
        if raw_file_ids:
            raw_files = db.query(RawFile).filter(RawFile.id.in_(raw_file_ids)).all()
            filename_by_raw = {rf.id: rf.filename for rf in raw_files}
        filename_map = {
            a.id: filename_by_raw.get(a.raw_file_id, "")
            for a in analyses if a.raw_file_id
        }

    return ReportsListResponse(
        reports=[
            ReportListItem(
                id=r.id,
                analysis_id=r.analysis_id or "",
                filename=filename_map.get(r.analysis_id, ""),
                created_at=r.created_at,
            )
            for r in reports
        ],
        total=len(reports),
    )
