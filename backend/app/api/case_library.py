"""Case Library API: anonymous contribution of analysis data."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.api.analysis import _build_category_map
from app.api.common import load_analysis, load_trades, get_raw_file_ids, get_raw_file_filenames
from app.database import get_db
from app.models.case_library import CaseLibrary
from app.models.raw_file import RawFile
from app.models.report import Report
from app.models.user import User
from app.engine.market_fetcher import ensure_market_data
from app.engine.pattern import PatternEngine
from app.engine.position import PositionBuilder

router = APIRouter(prefix="/api/case-library", tags=["case_library"])


class ContributeRequest(BaseModel):
    consent: bool
    analysis_id: str = ""


def _decode_raw_content(raw_content: bytes) -> str:
    """Decode raw file bytes to text, trying common encodings."""
    for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return raw_content.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw_content.decode("utf-8", errors="replace")


def _serialize_trades(trades) -> list[dict]:
    """Serialize trade records to a list of dicts for JSON storage."""
    return [
        {
            "symbol": t.symbol,
            "asset_type": t.asset_type,
            "datetime": str(t.datetime),
            "side": t.side,
            "quantity": t.quantity,
            "price": t.price,
            "commission": t.commission,
        }
        for t in trades
    ]


def _serialize_positions(positions) -> list[dict]:
    """Serialize PositionResult objects to dicts for JSON storage."""
    return [
        {
            "symbol": p.symbol,
            "asset_type": p.asset_type,
            "entry_date": str(p.entry_date),
            "exit_date": str(p.exit_date),
            "holding_days": p.holding_days,
            "total_quantity": p.total_quantity,
            "avg_entry_price": p.avg_entry_price,
            "avg_exit_price": p.avg_exit_price,
            "pnl": p.pnl,
            "pnl_pct": p.pnl_pct,
            "cost_known": p.cost_known,
        }
        for p in positions
    ]


def _build_stats_snapshot(trades, positions) -> dict:
    """Compute a lightweight stats snapshot matching the stats endpoint shape."""
    total_trades = len(trades)
    total_positions = len(positions)
    valid_positions = [p for p in positions if getattr(p, "cost_known", True)]
    valid_count = len(valid_positions)
    win_count = sum(1 for p in valid_positions if p.pnl > 0)
    win_rate = round(win_count / valid_count, 2) if valid_count > 0 else 0.0
    total_pnl = sum(p.pnl for p in valid_positions)

    return {
        "total_trades": total_trades,
        "total_positions": total_positions,
        "win_count": win_count,
        "win_rate": win_rate,
        "total_pnl": round(total_pnl, 2),
        "positions": _serialize_positions(positions),
    }


@router.post("/contribute")
def contribute(
    body: ContributeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Anonymous case contribution: contribute analysis data to the library."""
    # Consent = false: skip, record nothing
    if not body.consent:
        return {"detail": "已跳过"}

    # Consent = true: require analysis_id
    analysis_id = body.analysis_id.strip() if body.analysis_id else ""
    if not analysis_id:
        raise HTTPException(status_code=400, detail="analysis_id is required when consent=true")

    # Load analysis (ownership check)
    analysis = load_analysis(analysis_id, current_user.id, db)

    # Check duplicate: same analysis_id cannot be contributed twice
    existing = (
        db.query(CaseLibrary)
        .filter(CaseLibrary.analysis_id == analysis_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="该分析已贡献过，不能重复贡献",
        )

    # --- Collect data ---

    # 1. Trades
    trades = load_trades(analysis, current_user.id, db)
    trades_json = json.dumps(_serialize_trades(trades), ensure_ascii=False)

    # 2. Positions
    positions = PositionBuilder.build(trades)
    positions_json = json.dumps(_serialize_positions(positions), ensure_ascii=False)

    # 3. Stats snapshot
    stats_data = _build_stats_snapshot(trades, positions)
    stats_json = json.dumps(stats_data, ensure_ascii=False)

    # 4. Patterns (optional — computed lazily)
    patterns_json = None
    try:
        symbols = list({p.symbol for p in positions})
        market_data = {}
        if symbols:
            market_data = ensure_market_data(db, symbols, analysis.date_start, analysis.date_end)
        category_map = _build_category_map(positions, trades=trades, market_data=market_data)
        # Convert category_map {index: {category: pattern}} to list
        patterns_list = {}
        for idx, cats in category_map.items():
            pos = positions[idx]
            patterns_list[idx] = {
                "symbol": pos.symbol,
                "patterns": cats,
            }
        patterns_json = json.dumps(patterns_list, ensure_ascii=False)
    except Exception:
        patterns_json = None

    # 5. Report content (optional)
    report_content = None
    report = (
        db.query(Report)
        .filter(Report.analysis_id == analysis_id, Report.user_id == current_user.id)
        .order_by(Report.created_at.desc())
        .first()
    )
    if report:
        report_content = report.report_content

    # 6. Raw file content and filename
    raw_file_ids = get_raw_file_ids(analysis.id, db)
    raw_file_content_parts: list[str] = []
    raw_filenames: list[str] = []
    if raw_file_ids:
        raw_files = (
            db.query(RawFile)
            .filter(RawFile.id.in_(raw_file_ids), RawFile.user_id == current_user.id)
            .all()
        )
        for rf in raw_files:
            raw_filenames.append(rf.filename)
            raw_file_content_parts.append(
                _decode_raw_content(rf.raw_content)
            )
    raw_file_content = "\n".join(raw_file_content_parts)
    raw_filename = "; ".join(raw_filenames)

    # --- Store ---
    case = CaseLibrary(
        user_id=current_user.id,
        analysis_id=analysis_id,
        trades_json=trades_json,
        positions_json=positions_json,
        stats_json=stats_json,
        patterns_json=patterns_json,
        report_content=report_content,
        raw_file_content=raw_file_content,
        raw_filename=raw_filename,
    )
    db.add(case)
    db.commit()

    return JSONResponse(
        content={"detail": "案例已匿名贡献，感谢您的支持"},
        status_code=201,
    )


@router.get("/status")
def get_contribute_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check whether the current user has ever contributed a case."""
    has_consented = (
        db.query(CaseLibrary)
        .filter(CaseLibrary.user_id == current_user.id)
        .first()
    ) is not None
    return {"has_consented": has_consented}
