"""Upload API routes: upload file, confirm format, import trades."""

import hashlib
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Header, Request
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.analysis import Analysis, AnalysisFile
from app.models.raw_file import RawFile
from app.models.report import Report
from app.models.trade import Trade
from app.models.user import User
from app.parsers.registry import ParserRegistry
from app.ratelimit import limiter
from app.schemas.upload import (
    ConfirmRequest,
    ConfirmResponse,
    DetectResult,
    ImportRequest,
    ImportResponse,
    TradeDataResponse,
    UploadResponse,
)

router = APIRouter(prefix="/api/upload", tags=["upload"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = (".csv", ".xls", ".xlsx")

# ── File storage ────────────────────────────────────────────────────────────

UPLOAD_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"


def _make_file_path(user_id: str, raw_file_id: str, ext: str) -> str:
    """Return relative path: uploads/{user_id}/{raw_file_id}.ext"""
    return f"{user_id}/{raw_file_id}{ext}"


def _read_raw_content(rf: RawFile) -> bytes:
    """Read a RawFile's content from disk (backward compat with parser API)."""
    if not rf.file_path:
        return b""
    full_path = UPLOAD_ROOT / rf.file_path
    return full_path.read_bytes() if full_path.exists() else b""


def _delete_raw_file(rf: RawFile) -> None:
    """Remove raw file from disk (used during clear_trades)."""
    if not rf.file_path:
        return
    full_path = UPLOAD_ROOT / rf.file_path
    try:
        full_path.unlink(missing_ok=True)
    except OSError:
        pass


@router.post("", response_model=UploadResponse)
@limiter.limit("10/minute")
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    content_length: int | None = Header(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a raw trade file, save to DB, detect format candidates."""
    # Check content length first if provided
    if content_length and content_length > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    # Check file extension
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only CSV/XLS/XLSX files are allowed")

    # Read with size cap to prevent OOM (read 1 byte more to detect overflow)
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    # 计算内容哈希，检查是否重复上传
    content_hash = hashlib.sha256(content).hexdigest()
    existing = (
        db.query(RawFile)
        .filter(
            RawFile.user_id == current_user.id,
            RawFile.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"此文件已上传过（文件名：{existing.filename}），请勿重复上传。",
        )

    raw_file = RawFile(
        user_id=current_user.id,
        filename=filename,
        content_hash=content_hash,
    )
    db.add(raw_file)
    db.flush()  # get raw_file.id before writing to disk

    # Write file to disk under uploads/{user_id}/{raw_file_id}.{ext}
    ext = os.path.splitext(filename)[1].lower()
    rel_path = _make_file_path(current_user.id, raw_file.id, ext)
    full_path = UPLOAD_ROOT / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)

    raw_file.file_path = rel_path
    raw_file.file_size = len(content)
    db.commit()
    db.refresh(raw_file)

    detected = ParserRegistry.detect_format(content, file.filename or "unknown.csv")
    detected_formats = [
        DetectResult(source_type=st, asset_type=at, score=s)
        for st, at, s in detected
    ]

    return UploadResponse(
        raw_file_id=raw_file.id,
        detected_formats=detected_formats,
    )


@router.post("/confirm", response_model=ConfirmResponse)
def confirm_format(
    body: ConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm source format, parse file, and return trade preview."""
    raw_file = (
        db.query(RawFile)
        .filter(RawFile.id == body.raw_file_id, RawFile.user_id == current_user.id)
        .first()
    )
    if not raw_file:
        raise HTTPException(status_code=404, detail="Raw file not found")

    parser_cls = ParserRegistry.get_parser(body.source_type)
    if not parser_cls:
        raise HTTPException(
            status_code=400, detail=f"Unknown source type: {body.source_type}"
        )

    content = _read_raw_content(raw_file)
    trades = parser_cls.parse(content, raw_file.filename)

    # Persist the chosen format
    raw_file.source_type = body.source_type
    raw_file.asset_type = parser_cls.asset_type()
    db.commit()

    trade_responses = [
        TradeDataResponse(
            datetime=t.datetime,
            symbol=t.symbol,
            exchange=t.exchange,
            side=t.side,
            quantity=t.quantity,
            price=t.price,
            commission=t.commission,
            margin=t.margin,
            multiplier=t.multiplier,
        )
        for t in trades
    ]

    return ConfirmResponse(trades=trade_responses, count=len(trade_responses))


@router.post("/import", response_model=ImportResponse)
def import_trades(
    body: ImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parse confirmed file and save all trades to the database."""
    raw_file = (
        db.query(RawFile)
        .filter(RawFile.id == body.raw_file_id, RawFile.user_id == current_user.id)
        .first()
    )
    if not raw_file:
        raise HTTPException(status_code=404, detail="Raw file not found")
    if not raw_file.source_type:
        raise HTTPException(
            status_code=400, detail="Source type not set. Confirm format first."
        )

    parser_cls = ParserRegistry.get_parser(raw_file.source_type)
    if not parser_cls:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source type: {raw_file.source_type}",
        )

    content = _read_raw_content(raw_file)
    trades = parser_cls.parse(content, raw_file.filename)

    if not trades:
        return ImportResponse(imported_count=0, skipped_count=0)

    # 构建本次导入交易唯一键集合 (datetime, symbol, exchange, side, qty, price)
    incoming_keys = {
        (
            t.datetime.replace(microsecond=0),
            t.symbol,
            t.exchange,
            t.side,
            t.quantity,
            t.price,
        )
        for t in trades
    }

    # 批量查询用户全局已有交易，构建已有唯一键集合
    existing_rows = (
        db.query(
            Trade.datetime,
            Trade.symbol,
            Trade.exchange,
            Trade.side,
            Trade.quantity,
            Trade.price,
        )
        .filter(
            Trade.user_id == current_user.id,
            Trade.is_deleted.is_(False),
        )
        .all()
    )
    existing_keys = {
        (dt.replace(microsecond=0), sym, ex, side, qty, price)
        for dt, sym, ex, side, qty, price in existing_rows
    }

    # 过滤：只写入新交易
    imported = 0
    skipped = 0
    for t in trades:
        key = (
            t.datetime.replace(microsecond=0),
            t.symbol,
            t.exchange,
            t.side,
            t.quantity,
            t.price,
        )
        if key in existing_keys:
            skipped += 1
            continue
        db.add(
            Trade(
                raw_file_id=raw_file.id,
                user_id=current_user.id,
                asset_type=raw_file.asset_type or parser_cls.asset_type(),
                datetime=t.datetime,
                symbol=t.symbol,
                exchange=t.exchange,
                side=t.side,
                quantity=t.quantity,
                price=t.price,
                commission=t.commission,
                margin=t.margin,
                multiplier=t.multiplier,
            )
        )
        existing_keys.add(key)  # 同文件内去重
        imported += 1

    if imported > 0:
        db.commit()

    return ImportResponse(imported_count=imported, skipped_count=skipped)


@router.delete("/trades", status_code=status.HTTP_200_OK)
def clear_trades(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete all trading data for the current user.

    Deletes in FK-safe order: reports → analyses (join table + rows) →
    trades → raw files. This is irreversible.
    """
    user_id = current_user.id

    # 1. Reports (child of Analysis)
    analysis_ids = [
        row[0] for row in
        db.query(Analysis.id).filter(Analysis.user_id == user_id).all()
    ]
    if analysis_ids:
        db.query(Report).filter(Report.analysis_id.in_(analysis_ids)).delete(synchronize_session=False)

    # 2. AnalysisFiles (join table)
    if analysis_ids:
        db.query(AnalysisFile).filter(AnalysisFile.analysis_id.in_(analysis_ids)).delete(synchronize_session=False)

    # 3. Analyses
    db.query(Analysis).filter(Analysis.user_id == user_id).delete(synchronize_session=False)

    # 4. Trades
    db.query(Trade).filter(Trade.user_id == user_id).delete(synchronize_session=False)

    # 5. RawFiles — delete files from disk first, then rows
    raw_files = db.query(RawFile).filter(RawFile.user_id == user_id).all()
    for rf in raw_files:
        _delete_raw_file(rf)
    db.query(RawFile).filter(RawFile.user_id == user_id).delete(synchronize_session=False)

    # Clean up empty user upload directories
    user_upload_dir = UPLOAD_ROOT / user_id
    try:
        shutil.rmtree(user_upload_dir, ignore_errors=True)
    except OSError:
        pass

    db.commit()
    return {"detail": "所有交易数据已永久删除"}
