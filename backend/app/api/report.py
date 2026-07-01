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


def _build_analysis_data(trades, positions, insight_items, whatif_items, stats_data: dict = None, report_date: str = "", date_start: str = "", date_end: str = "", baseline_expectancy: float = None, shapley_items: list = None, scenario_results: list = None) -> dict:
    """Build the analysis_data dict expected by build_user_prompt.

    When stats_data is provided (V4.0), risk metrics and positions summary
    are included for richer AI diagnosis. AI_INPUT_CONTRACT 字段：
    baseline_expectancy（评价基准）、shapley_items（赚钱来源归因）、
    scenario_results（情景回测：5个规则的delta，V1.2.3）。
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
    # AI_INPUT_CONTRACT V1.2.3: 情景回测——5个规则的delta喂给AI
    # delta = 应用规则后收益率 − 现状值，正=改善，负=拉低（与what_if的delta语义不同，独立成段）
    if scenario_results:
        result["scenario_backtest"] = scenario_results
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

    # V1.2.3: 情景回测——5个规则反事实模拟，喂给AI做scenario_backtest段
    # delta = 应用规则后收益率 − 现状值，正=该规则改善收益（与whatif的delta语义不同）
    def _run_scenario(rt, params, label):
        r = ProfitAttribution.analyze_rule(
            valid_positions, rule_type=rt, params=params, market_data=market_data
        )
        if not r:
            return None
        return {
            "rule_name": label,
            "affected_positions": r["affected_positions"],
            "original_return": r["original_return"],
            "what_if_return": r["what_if_return"],
            "delta": r["delta"],
        }

    scenario_results = [
        r for r in [
            _run_scenario("stop_loss", {"loss_pct": 0.08}, "固定8%止损"),
            _run_scenario("stop_loss_large_loss", {"loss_pct": 0.08, "large_loss_pct": -0.08}, "仅大亏止损"),
            _run_scenario("trailing_stop", {"trail_pct": 0.08}, "移动止损8%"),
            _run_scenario("take_profit", {"profit_pct": 0.10}, "固定止盈10%"),
            _run_scenario("trailing_take_profit", {"activation_pct": 0.05, "trail_pct": 0.05}, "移动止盈5%/5%"),
        ] if r
    ]

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

    # V4.0: stats-level metrics for the AI prompt.
    # Source from analysis.stats_snapshot (the EXACT value the /stats panel
    # shows) so the AI can never diverge from what the user sees. The previous
    # inline recompute drifted — its max_drawdown_pct used the old `peak`-only
    # denominator while compute.py/analysis.py moved to `total_invested + peak`
    # in V1.1.2 (P0-1). Fall back to compute_stats only for legacy analyses
    # without a snapshot. AI_INPUT_CONTRACT护栏 fields (is_small_sample /
    # avg_*_holding_days) are not in the snapshot, so merge them in here.
    if analysis.stats_snapshot:
        stats_data = dict(analysis.stats_snapshot)
    else:
        from app.engine.compute import compute_stats as _compute_stats
        stats_data = _compute_stats(analysis, trades, db).model_dump(mode="json")
    # Strip legacy snapshot-only keys that aren't AI-input contract fields.
    stats_data.pop("snapshot_raw_file_id", None)
    stats_data.pop("snapshot_raw_file_ids", None)
    # Merge护栏 fields (not stored in stats_snapshot).
    stats_data["is_small_sample"] = is_small_sample
    stats_data["avg_win_holding_days"] = round(avg_win_holding, 1)
    stats_data["avg_loss_holding_days"] = round(avg_loss_holding, 1)

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
        scenario_results=scenario_results,
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
