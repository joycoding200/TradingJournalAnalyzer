"""Report API routes: generate AI report, fetch report(s)."""

import io
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.ai.prompt import SYSTEM_PROMPT, build_user_prompt
from app.ai.provider import get_llm
from app.ai.sanitizer import sanitize_report
from app.ai.validator import ReportValidator, generate_with_retry
from app.auth.jwt import get_current_user
from app.api.common import load_analysis, load_trades
from app.config import settings
from app.database import get_db
from app.models.analysis import Analysis
from app.models.report import Report
from app.models.trade import Trade
from app.models.user import User
from app.engine.pattern import PatternEngine
from app.engine.position import PositionBuilder
from app.engine.whatif import ProfitAttribution
from app.engine.market_fetcher import ensure_market_data
from app.ratelimit import limiter
from app.schemas.report import (
    ReportCheckResponse,
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportListItem,
    ReportResponse,
    ReportsListResponse,
)

router = APIRouter(prefix="/api", tags=["report"])


# AI_INPUT_CONTRACT: 标签维度归属（中文），用于 prompt 渲染，区分确定结论与心理推测
_DIM_CN = {
    "market_env": "市场环境",
    "behavior": "交易行为",
    "outcome": "交易结果",
    "psychology": "心理推测",
}


def _pattern_dimension(pattern_name: str) -> str:
    """Return Chinese dimension name for a pattern tag."""
    from app.engine.insight import InsightEngine
    dim = InsightEngine._dim_for_pattern(pattern_name)
    return _DIM_CN.get(dim, dim)


def _compute_date_segments(trades, gap_days: int = 14) -> str:
    """Compute the actual date range(s) from trade data, detecting gaps.

    If trade dates are continuous (no gap > gap_days), returns a single range.
    If there are gaps, returns multiple segments joined by '、'.
    Example: "2026-01-05 至 2026-03-31、2026-06-01 至 2026-06-17"
    """
    if not trades:
        return "无数据"

    dates = sorted({t.datetime.date() for t in trades})
    if not dates:
        return "无数据"

    segments = []
    seg_start = dates[0]
    prev = dates[0]

    for d in dates[1:]:
        if (d - prev).days > gap_days:
            segments.append((seg_start, prev))
            seg_start = d
        prev = d
    segments.append((seg_start, prev))

    if len(segments) == 1:
        return f"{segments[0][0]} 至 {segments[0][1]}"
    return "、".join(f"{s} 至 {e}" for s, e in segments)


def _build_analysis_data(trades, positions, insight_items, whatif_items, stats_data: dict = None, report_date: str = "", date_start: str = "", date_end: str = "", baseline_expectancy: float = None, shapley_items: list = None) -> dict:
    """Build the analysis_data dict expected by build_user_prompt.

    When stats_data is provided (V4.0), risk metrics and positions summary
    are included for richer AI diagnosis. AI_INPUT_CONTRACT 字段：
    baseline_expectancy（评价基准）、shapley_items（赚钱来源归因）。
    """
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

    result = {
        "report_date": report_date,
        "date_start": date_start,
        "date_end": date_end,
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
                "avg_pnl_pct": i.avg_pnl_pct,
                # AI_INPUT_CONTRACT: 维度归属，防 AI 漏看某维度、区分确定结论与心理推测
                "dimension": _pattern_dimension(i.pattern_name),
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
    # AI_INPUT_CONTRACT: 评价基准 + 赚钱来源归因
    if baseline_expectancy is not None:
        result["baseline_expectancy"] = round(baseline_expectancy, 2)
    if shapley_items:
        result["shapley"] = shapley_items

    # V4.0: enrich with stats-level risk metrics
    if stats_data:
        result["profit_factor"] = stats_data.get("profit_factor")
        result["expectancy"] = stats_data.get("expectancy")
        result["max_drawdown"] = stats_data.get("max_drawdown")
        result["max_drawdown_pct"] = stats_data.get("max_drawdown_pct")
        result["consecutive_losses"] = stats_data.get("consecutive_losses")
        result["avg_mae"] = stats_data.get("avg_mae")
        result["avg_mfe"] = stats_data.get("avg_mfe")
        result["profit_capture_ratio"] = stats_data.get("profit_capture_ratio")
        result["win_loss_ratio"] = stats_data.get("win_loss_ratio")
        result["total_return_pct"] = stats_data.get("total_return_pct")
        result["pnl_distribution"] = stats_data.get("pnl_distribution", [])

        # V4.0: top 3 winners + bottom 3 losers
        sorted_by_pnl = sorted(positions, key=lambda p: p.pnl, reverse=True)
        top3 = sorted_by_pnl[:3]
        bottom3 = sorted_by_pnl[-3:]
        result["positions_summary"] = {
            "top_winners": [
                {
                    "symbol": p.symbol,
                    "pnl": round(p.pnl, 2),
                    "pnl_pct": round(p.pnl_pct, 4),
                    "holding_days": p.holding_days,
                    "entry_date": str(p.entry_date),
                    "exit_date": str(p.exit_date),
                }
                for p in top3
            ],
            "top_losers": [
                {
                    "symbol": p.symbol,
                    "pnl": round(p.pnl, 2),
                    "pnl_pct": round(p.pnl_pct, 4),
                    "holding_days": p.holding_days,
                    "entry_date": str(p.entry_date),
                    "exit_date": str(p.exit_date),
                }
                for p in reversed(bottom3)  # most negative first
            ],
        }

    return result


@router.post(
    "/report/generate",
    response_model=ReportGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def generate_report(
    request: Request,
    body: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run full pipeline, build AI prompt, call LLM, validate, save report."""
    analysis = load_analysis(body.analysis_id, current_user.id, db)
    trades = load_trades(analysis, current_user.id, db)
    positions = PositionBuilder.build(trades)

    # Fetch market data for pattern tagging
    market_data = {}
    symbols = list({p.symbol for p in positions})
    if symbols:
        market_data = ensure_market_data(db, symbols, analysis.date_start, analysis.date_end)

    # Build patterns map with confidence scores (including market env patterns)
    # Detect psychology patterns once for all positions
    psychology_results = PatternEngine.detect_psychological_patterns(positions, all_trades=trades)
    psyche_by_pos: dict[int, list] = {}
    for idx, psy_result in psychology_results:
        psyche_by_pos.setdefault(idx, []).append(psy_result)

    # Tag once; reuse the PatternResult lists for BOTH the WhatIf patterns_map
    # and _build_category_map (which would otherwise re-tag the whole set a
    # second time — PatternEngine cost doubled for large position sets).
    # Output is identical to the previous double-tagging path: same results,
    # same resolve_per_category. See test_build_category_map_precomputed_matches.
    results_by_pos: dict[int, list] = {}
    patterns_map: dict[int, list[tuple[str, float]]] = {}
    for i, pos in enumerate(positions):
        results = PatternEngine.tag_position(pos, positions, trades=trades, all_trades=trades)
        if market_data:
            results.extend(PatternEngine.tag_market_patterns(pos, market_data))
        results = PatternEngine.resolve_hierarchy(results)
        if i in psyche_by_pos:
            results.extend(psyche_by_pos[i])
        results_by_pos[i] = results
        patterns_map[i] = [(r.pattern_name, r.confidence) for r in results]

    # Prefer the cached insight snapshot so the AI report reasons over the
    # EXACT same patterns the /insight panel shows (which also reads the
    # snapshot). Recomputing here with current market data diverges from the
    # snapshot (built at run_analysis time) whenever market data shifts
    # between calls — the source of the report/insight patterns flake. Only
    # legacy analyses without a snapshot fall back to recomputation.
    # See TestReportInsightConsistency.
    if analysis.insight_snapshot:
        from app.schemas.analysis import InsightResponse
        insight_resp = InsightResponse(**analysis.insight_snapshot)
        insight_items = insight_resp.patterns
        baseline_expectancy = insight_resp.baseline_expectancy
    else:
        from app.engine.compute import _build_category_map, compute_insight
        category_map = _build_category_map(
            positions, trades, market_data, precomputed=results_by_pos
        )
        insight_resp = compute_insight(positions, trades, category_map)
        insight_items = insight_resp.patterns
        baseline_expectancy = insight_resp.baseline_expectancy

    # WhatIf uses all patterns (not just primary)
    patterns_map_names: dict[int, list[str]] = {
        i: [name for name, _ in pats] for i, pats in patterns_map.items()
    }
    whatif_items = ProfitAttribution.attribution_analysis(positions, patterns_map_names)

    # V4.0: compute stats-level metrics for richer AI prompt
    valid_positions = [p for p in positions if getattr(p, "cost_known", True)]
    valid_count = len(valid_positions)

    # AI_INPUT_CONTRACT: 护栏字段 — 小样本标识（<5笔）+ 盈亏持仓天数对比
    is_small_sample = valid_count < 5
    win_positions_h = [p for p in valid_positions if p.pnl > 0]
    loss_positions_h = [p for p in valid_positions if p.pnl <= 0]
    avg_win_holding = (
        sum(p.holding_days for p in win_positions_h) / len(win_positions_h)
        if win_positions_h else 0.0
    )
    avg_loss_holding = (
        sum(p.holding_days for p in loss_positions_h) / len(loss_positions_h)
        if loss_positions_h else 0.0
    )

    # AI_INPUT_CONTRACT: Shapley 归因（招牌功能"赚钱来源分析"，需 valid_positions）
    from app.engine.attribution import shapley_attribution
    shapley_values = shapley_attribution(positions, patterns_map_names)
    total_pnl_for_shapley = sum(p.pnl for p in valid_positions)
    shapley_summary = sorted(shapley_values.items(), key=lambda x: -x[1])
    shapley_items = [
        {
            "pattern_name": pat,
            "shapley_value": val,
            "pct_of_total": round(val / abs(total_pnl_for_shapley) * 100, 1)
            if total_pnl_for_shapley != 0 else 0.0,
        }
        for pat, val in shapley_summary
    ]

    win_positions = [p for p in valid_positions if p.pnl > 0]
    loss_positions = [p for p in valid_positions if p.pnl <= 0]
    total_gross_profit = sum(p.pnl for p in win_positions)
    total_gross_loss = abs(sum(p.pnl for p in loss_positions))
    profit_factor = total_gross_profit / total_gross_loss if total_gross_loss > 0 else None
    total_pnl_val = sum(p.pnl for p in valid_positions)
    total_invested = sum(p.avg_entry_price * p.total_quantity for p in valid_positions)
    total_return_pct = total_pnl_val / total_invested if total_invested > 0 else 0.0
    avg_win_amount = sum(p.pnl for p in win_positions) / len(win_positions) if win_positions else 0.0
    avg_loss_amount = sum(p.pnl for p in loss_positions) / len(loss_positions) if loss_positions else 0.0
    win_loss_ratio = avg_win_amount / abs(avg_loss_amount) if avg_loss_amount != 0 else None

    # Consecutive losses
    sorted_by_date = sorted(valid_positions, key=lambda p: p.exit_date)
    streak, max_streak = 0, 0
    for p in sorted_by_date:
        if p.pnl <= 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # Max drawdown
    cum_pnl, peak, max_dd = 0.0, 0.0, 0.0
    for p in sorted_by_date:
        cum_pnl += p.pnl
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd
    dd_denom = peak if peak > 0 else (total_invested if total_invested > 0 else 0.0)
    max_drawdown_pct = (max_dd / dd_denom) if dd_denom > 0 else 0.0

    # MAE/MFE
    mae_mfe_stats = {}
    symbols = list({p.symbol for p in valid_positions})
    if symbols and market_data:
        from app.engine.mae import compute_mae_mfe_stats as _compute_mae
        mae_mfe_stats = _compute_mae(valid_positions, market_data)

    # Expectancy
    from app.engine.insight import InsightItem
    expectancy_val = InsightItem.compute(valid_positions) if valid_positions else 0.0

    # PnL level distribution (NOT behavioral outcome patterns)
    pnl_counts: dict[str, int] = {}
    for p in valid_positions:
        level_info = PatternEngine.classify_pnl_level(p)
        level = level_info["level"]
        if level:
            pnl_counts[level] = pnl_counts.get(level, 0) + 1
    pnl_dist = [{"level": l, "count": c} for l, c in sorted(pnl_counts.items())]

    stats_data = {
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "expectancy": round(expectancy_val, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "consecutive_losses": max_streak,
        "avg_mae": round(mae_mfe_stats.get("avg_mae", 0.0), 4),
        "avg_mfe": round(mae_mfe_stats.get("avg_mfe", 0.0), 4),
        "profit_capture_ratio": round(mae_mfe_stats.get("profit_capture_ratio", 0.0), 4),
        "win_loss_ratio": round(win_loss_ratio, 2) if win_loss_ratio is not None else None,
        "total_return_pct": round(total_return_pct, 4),
        "pnl_distribution": pnl_dist,
        # AI_INPUT_CONTRACT 护栏字段
        "is_small_sample": is_small_sample,
        "avg_win_holding_days": round(avg_win_holding, 1),
        "avg_loss_holding_days": round(avg_loss_holding, 1),
    }

    # Build AI prompt with exact dates (so the AI doesn't guess)
    from datetime import date as date_type
    today_str = date_type.today().isoformat()
    date_range_str = _compute_date_segments(trades)
    analysis_data = _build_analysis_data(
        trades, positions, insight_items, whatif_items, stats_data,
        report_date=today_str,
        date_start=date_range_str,  # now contains full segment info
        date_end="",  # no longer used individually
        baseline_expectancy=baseline_expectancy,
        shapley_items=shapley_items,
    )
    user_prompt = build_user_prompt(analysis_data)

    # Call LLM
    provider = get_llm()
    report_content = await generate_with_retry(
        provider, SYSTEM_PROMPT, user_prompt, analysis_data
    )

    # Sanitize XSS vectors before saving (P1-14)
    report_content = sanitize_report(report_content)

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


@router.get("/report/by-analysis/{analysis_id}", response_model=ReportCheckResponse)
def check_report_by_analysis(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if a report exists for the given analysis."""
    report = (
        db.query(Report)
        .filter(Report.analysis_id == analysis_id, Report.user_id == current_user.id)
        .first()
    )
    if report:
        return ReportCheckResponse(exists=True, report_id=report.id)
    return ReportCheckResponse(exists=False)


@router.get("/report/{report_id}/download")
def download_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download report as .md file."""
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    content = report.report_content.encode("utf-8")
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=report_{report_id[:8]}.md"
        },
    )


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
    from app.models.analysis import AnalysisFile
    from app.api.common import get_raw_file_ids, get_raw_file_filenames

    reports = (
        db.query(Report)
        .filter(Report.user_id == current_user.id)
        .order_by(Report.created_at.desc())
        .limit(50)
        .all()
    )

    analysis_ids = [r.analysis_id for r in reports if r.analysis_id]
    # Resolve filenames via association table for multi-file support
    analysis_first_filename: dict[str, str] = {}
    if analysis_ids:
        all_raw_file_ids: set[str] = set()
        for aid in analysis_ids:
            file_ids = get_raw_file_ids(aid, db)
            if file_ids:
                analysis_first_filename[aid] = file_ids[0]  # temporary; replaced below
                all_raw_file_ids.update(file_ids)
        filename_by_raw = get_raw_file_filenames(list(all_raw_file_ids), db)
        for aid in analysis_ids:
            file_ids = get_raw_file_ids(aid, db)
            first = file_ids[0] if file_ids else ""
            analysis_first_filename[aid] = filename_by_raw.get(first, "")

    return ReportsListResponse(
        reports=[
            ReportListItem(
                id=r.id,
                analysis_id=r.analysis_id or "",
                filename=analysis_first_filename.get(r.analysis_id, ""),
                username=(current_user.email or "").split("@")[0],
                created_at=r.created_at,
            )
            for r in reports
        ],
        total=len(reports),
    )
