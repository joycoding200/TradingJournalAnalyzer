"""Analysis API routes: run analysis, fetch stats / insight / what-if."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.api.common import load_analysis, load_trades, get_raw_file_ids, get_raw_file_filenames, build_symbol_name_map
from app.database import get_db
from app.models.analysis import Analysis, AnalysisFile
from app.models.trade import Trade
from app.models.user import User
from app.models.raw_file import RawFile
from app.engine.compute import (
    _build_category_map,
    compute_insight,
    compute_stats,
    compute_whatif,
    persist_snapshot,
)
from app.engine.mae import compute_mae_mfe_stats
from app.engine.market_fetcher import ensure_market_data
from app.engine.pattern import PatternEngine
from app.engine.position import PositionBuilder
from app.ratelimit import limiter
from app.schemas.analysis import (
    AnalysisListItem,
    AnalysisListResponse,
    AnalysisRunRequest,
    AnalysisRunResponse,
    AttributionItem,
    EquityPoint,
    InsightPatternItem,
    InsightResponse,
    CrossAnalysisItem,
    LinkFilesRequest,
    PnlLevelItem,
    PositionItem,
    RuleSimulationItem,
    ShapleyItem,
    StatsResponse,
    SymbolSummaryItem,
    WhatIfResponse,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post(
    "/run",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
def run_analysis(
    request: Request,
    body: AnalysisRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an analysis record for the given date range + uploaded file(s).

    Supports both legacy single-file (raw_file_id) and new multi-file
    (raw_file_ids) modes. Files must belong to the current user.
    """
    # Collect all file IDs from both legacy and new fields
    all_file_ids: list[str] = []
    if body.raw_file_id:
        all_file_ids.append(body.raw_file_id)
    all_file_ids.extend(body.raw_file_ids)
    all_file_ids = list(dict.fromkeys(all_file_ids))  # deduplicate, preserve order

    # Validate all raw_files belong to current user
    if all_file_ids:
        raw_files = (
            db.query(RawFile)
            .filter(RawFile.id.in_(all_file_ids), RawFile.user_id == current_user.id)
            .all()
        )
        if len(raw_files) != len(all_file_ids):
            raise HTTPException(
                status_code=404, detail="One or more raw files not found or not owned by user"
            )

    analysis = Analysis(
        user_id=current_user.id,
        date_start=body.date_start,
        date_end=body.date_end,
        raw_file_id=all_file_ids[0] if all_file_ids else None,  # first file in legacy column
    )
    db.add(analysis)
    db.flush()  # get analysis.id before creating association rows

    # Create association table entries for all files
    for fid in all_file_ids:
        db.add(AnalysisFile(analysis_id=analysis.id, raw_file_id=fid))

    db.commit()
    db.refresh(analysis)

    # Pre-compute all analysis data and store as snapshots so subsequent
    # GET /stats, /insight, /whatif return instantly from JSONB columns.
    from app.engine.compute import compute_all  # lazy import to avoid circular deps
    # Capture the id up front: if compute_all fails the session is poisoned
    # (PendingRollbackError), and touching any analysis attribute in the
    # except handler would re-trigger a flush and raise again.
    aid = analysis.id
    try:
        trades = load_trades(analysis, current_user.id, db)
        stats, insight, whatif = compute_all(analysis, trades, db)
        analysis.stats_snapshot = stats.model_dump(mode="json")
        analysis.insight_snapshot = insight.model_dump(mode="json")
        analysis.whatif_snapshot = whatif.model_dump(mode="json")
        analysis.computed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        # Roll back the poisoned session so the Analysis row (already committed
        # above) stays usable and subsequent requests start from a clean state.
        # Without this, a flush error (e.g. duplicate daily_bars from mootdx)
        # leaves the session in PendingRollbackError, which then breaks every
        # later query — including get_stats's fallback path.
        db.rollback()
        logger.exception("compute_all failed for analysis %s", aid)
        # Don't block — user can still view analysis; data will be computed
        # on-demand by the GET endpoints (fallback path).

    # Use the pre-captured id (not analysis.id): after a rollback the session
    # is clean but accessing analysis.id would still trigger a refresh SELECT;
    # aid holds the same value and avoids the extra round-trip.
    return AnalysisRunResponse(analysis_id=aid, filename=body.filename or "")


@router.post("/{analysis_id}/link-files", status_code=status.HTTP_200_OK)
def link_files_to_analysis(
    analysis_id: str,
    body: LinkFilesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Link existing (already-imported) raw files to an analysis.

    Used to add more trading statements to an existing analysis.
    Does NOT re-import trades — each file must already be confirmed and imported.
    """
    analysis = load_analysis(analysis_id, current_user.id, db)

    # Validate raw_files exist and belong to user
    raw_files = (
        db.query(RawFile)
        .filter(RawFile.id.in_(body.raw_file_ids), RawFile.user_id == current_user.id)
        .all()
    )
    if len(raw_files) != len(body.raw_file_ids):
        raise HTTPException(status_code=404, detail="One or more raw files not found")

    # Check each raw_file has been imported (has source_type set)
    for rf in raw_files:
        if not rf.source_type:
            raise HTTPException(
                status_code=400,
                detail=f"文件 '{rf.filename}' 尚未导入，请先确认格式并导入。",
            )

    # Add to association table (skip duplicates)
    existing = get_raw_file_ids(analysis.id, db)
    added = 0
    for fid in body.raw_file_ids:
        if fid not in existing:
            db.add(AnalysisFile(analysis_id=analysis.id, raw_file_id=fid))
            added += 1

    # Invalidate snapshots so GET endpoints re-compute on next access.
    # Market data for existing symbols is already cached in daily_bars;
    # re-computation is fast.  Pre-computing here would block the request
    # on mootdx TCP fetches for any new symbols.
    if added > 0:
        analysis.stats_snapshot = None
        analysis.insight_snapshot = None
        analysis.whatif_snapshot = None

        # Flush the newly added AnalysisFile rows so the date-range query
        # below sees them even when the session has autoflush disabled.
        db.flush()

        # Recalculate date range to cover all linked files
        all_file_ids = get_raw_file_ids(analysis.id, db)
        trade_dates = (
            db.query(Trade.datetime)
            .filter(
                Trade.raw_file_id.in_(all_file_ids),
                Trade.user_id == current_user.id,
                Trade.is_deleted.is_(False),
            )
            .order_by(Trade.datetime)
            .all()
        )
        if trade_dates:
            analysis.date_start = trade_dates[0][0].date()
            analysis.date_end = trade_dates[-1][0].date()

        db.commit()
    return {"detail": f"已添加 {added} 个文件到分析", "raw_file_ids": body.raw_file_ids}


# Backward compatibility aliases
_load_analysis = load_analysis
_load_trades = load_trades


@router.get("/{analysis_id}/stats", response_model=StatsResponse)
@limiter.limit("30/minute")
def get_stats(
    request: Request,
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compute KPI stats and positions for the analysis."""
    analysis = _load_analysis(analysis_id, current_user.id, db)

    # Fast path: return pre-computed snapshot.
    # Self-heal: a legacy 12-field partial snapshot (written before the
    # model_dump() fix) is truthy but lacks required fields (positions,
    # max_win, max_loss, consecutive_losses, …), so StatsResponse(**snapshot)
    # raises ValidationError → 422 forever. Catch it, drop the stale snapshot,
    # and fall through to the slow path, which recomputes AND overwrites a
    # complete snapshot — healing the analysis for all future requests. See
    # test_stale_partial_snapshot_self_heals.
    if analysis.stats_snapshot:
        try:
            return StatsResponse(**analysis.stats_snapshot)
        except Exception:
            logger.warning(
                "stale/incomplete stats_snapshot for analysis %s, recomputing",
                analysis.id,
            )
            analysis.stats_snapshot = None
            # Fall through to slow path (no return here).

    # Slow path: compute on-demand (legacy analyses without snapshots, or when
    # run_analysis's compute_all failed at creation time — e.g. mootdx TCP errors
    # on the server). Reuses compute.compute_stats so the slow path can never
    # drift from compute_all (the drift guard test_compute_equivalence locks
    # this). Uses the serial ensure_market_data (not compute_all's parallel
    # fetcher) to avoid the PendingRollbackError that parallel daily_bars
    # inserts can trigger on this session.
    trades = _load_trades(analysis, current_user.id, db)
    response = compute_stats(analysis, trades, db)

    # compute_stats hardcodes MAE/MFE to 0.0 (it doesn't fetch market data);
    # patch them in here, mirroring compute_all's backfill. Fetch with the
    # serial ensure_market_data for the session-safety reason above.
    positions = PositionBuilder.build(trades)
    valid_positions = [p for p in positions if getattr(p, "cost_known", True)]
    symbols = list({p.symbol for p in valid_positions})
    if symbols:
        market_data = ensure_market_data(db, symbols, analysis.date_start, analysis.date_end)
        mae_mfe_stats = compute_mae_mfe_stats(valid_positions, market_data)
        response.avg_mae = round(mae_mfe_stats.get("avg_mae", 0.0), 4)
        response.avg_mfe = round(mae_mfe_stats.get("avg_mfe", 0.0), 4)
        response.mae_winners = round(mae_mfe_stats.get("mae_winners", 0.0), 4)
        response.mae_losers = round(mae_mfe_stats.get("mae_losers", 0.0), 4)
        response.profit_capture_ratio = round(mae_mfe_stats.get("profit_capture_ratio", 0.0), 4)

    # Cache the FULL StatsResponse snapshot so the fast path
    # (StatsResponse(**snapshot)) works on the next request. Storing the
    # complete model_dump() guarantees the round-trip (a prior 12-field
    # "summary" dict caused 422s — see test_snapshot_round_trip).
    snapshot = response.model_dump(mode="json")
    snapshot["snapshot_raw_file_id"] = analysis.raw_file_id  # legacy compat
    snapshot["snapshot_raw_file_ids"] = get_raw_file_ids(analysis.id, db)  # multi-file provenance
    persist_snapshot(db, analysis, "stats_snapshot", snapshot)

    return response


def _module_for_pattern(pattern_name: str) -> str:
    """Return the dimension name for a pattern (market_env/behavior/outcome/psychology).
    Delegates to PatternEngine.CATEGORY_MAP (single source)."""
    return PatternEngine.CATEGORY_MAP.get(pattern_name, "behavior")


@router.get("/{analysis_id}/insight", response_model=InsightResponse)
@limiter.limit("30/minute")
def get_insight(
    request: Request,
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the full pipeline and return pattern analysis."""
    analysis = _load_analysis(analysis_id, current_user.id, db)

    # Fast path: return pre-computed snapshot
    if analysis.insight_snapshot:
        return InsightResponse(**analysis.insight_snapshot)

    # Slow path: compute on-demand (legacy analyses without snapshots).
    # Reuses compute.compute_insight so the slow path can never drift from
    # compute_all (the drift guard test_compute_equivalence locks this).
    trades = _load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)

    # Fetch market data for entry-pattern tagging (CHASE/BOTTOM/BREAKOUT/TREND etc.)
    symbols = list({p.symbol for p in positions})
    market_data = {}
    if symbols:
        market_data = ensure_market_data(
            db, symbols, analysis.date_start, analysis.date_end
        )

    category_map = _build_category_map(positions, trades=trades, market_data=market_data)
    response = compute_insight(positions, trades, category_map)

    # Self-heal: persist the snapshot so the next request hits the fast path.
    # Mirrors get_stats. Without this, a failed compute_all at run_analysis
    # time leaves insight_snapshot permanently null and every GET re-runs the
    # full computation. See BUG-3 audit fix.
    persist_snapshot(db, analysis, "insight_snapshot", response.model_dump(mode="json"))
    return response


@router.get("/{analysis_id}/whatif", response_model=WhatIfResponse)
@limiter.limit("30/minute")
def get_whatif(
    request: Request,
    analysis_id: str,
    rule_type: str = "stop_loss",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run what-if analysis: factor contribution + stop-loss rule simulation."""
    analysis = _load_analysis(analysis_id, current_user.id, db)

    # Fast path: return pre-computed snapshot
    if analysis.whatif_snapshot:
        return WhatIfResponse(**analysis.whatif_snapshot)

    # Slow path: compute on-demand (legacy analyses without snapshots).
    # Reuses compute.compute_whatif so the slow path can never drift from
    # compute_all (the drift guard test_compute_equivalence locks this).
    trades = _load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)

    # Fetch market data for entry-pattern tagging
    symbols = list({p.symbol for p in positions})
    market_data = {}
    if symbols:
        market_data = ensure_market_data(
            db, symbols, analysis.date_start, analysis.date_end
        )

    category_map = _build_category_map(positions, trades=trades, market_data=market_data)
    response = compute_whatif(positions, category_map, market_data)

    # Self-heal: persist the snapshot so the next request hits the fast path.
    persist_snapshot(db, analysis, "whatif_snapshot", response.model_dump(mode="json"))
    return response


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all analyses for current user with filename and snapshots."""
    from app.models.report import Report

    analyses = (
        db.query(Analysis)
        .filter(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
        .limit(50)
        .all()
    )

    # Bulk fetch analysis-to-raw_file mappings from association table
    aids = [a.id for a in analyses]
    analyses_raw_ids: dict[str, list[str]] = {}
    all_raw_ids: set[str] = set()
    if aids:
        af_rows = (
            db.query(AnalysisFile.analysis_id, AnalysisFile.raw_file_id)
            .filter(AnalysisFile.analysis_id.in_(aids))
            .all()
        )
        for aid, rid in af_rows:
            analyses_raw_ids.setdefault(aid, []).append(rid)
            all_raw_ids.add(rid)
        # Fallback for legacy analyses not yet in association table
        for a in analyses:
            if a.id not in analyses_raw_ids and a.raw_file_id:
                analyses_raw_ids[a.id] = [a.raw_file_id]
                all_raw_ids.add(a.raw_file_id)

    # Bulk fetch filenames
    filename_map = get_raw_file_filenames(list(all_raw_ids), db)

    # Get reports linked to these analyses
    report_map: dict[str, str] = {}
    if aids:
        reports = db.query(Report).filter(Report.analysis_id.in_(aids)).all()
        report_map = {r.analysis_id: r.id for r in reports}

    return AnalysisListResponse(
        analyses=[
            AnalysisListItem(
                id=a.id,
                filename=filename_map.get(analyses_raw_ids.get(a.id, [None])[0], ""),
                filenames=[filename_map.get(fid, "") for fid in analyses_raw_ids.get(a.id, [])],
                raw_file_ids=analyses_raw_ids.get(a.id, []),
                date_start=a.date_start,
                date_end=a.date_end,
                created_at=a.created_at,
                has_snapshot=a.stats_snapshot is not None,
                has_report=a.id in report_map,
                report_id=report_map.get(a.id, ""),
            )
            for a in analyses
        ],
        total=len(analyses),
    )
