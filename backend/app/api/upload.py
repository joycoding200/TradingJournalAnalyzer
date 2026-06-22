"""Upload API routes: upload file, confirm format, import trades."""

import os
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Header
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_user
from app.database import get_db
from app.models.analysis import Analysis
from app.models.raw_file import RawFile
from app.models.trade import Trade
from app.models.user import User
from app.parsers.registry import ParserRegistry
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


@router.post("", response_model=UploadResponse)
def upload_file(
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

    # Read and check size
    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    raw_file = RawFile(
        user_id=current_user.id,
        filename=filename,
        raw_content=content,
    )
    db.add(raw_file)
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

    trades = parser_cls.parse(raw_file.raw_content, raw_file.filename)

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

    trades = parser_cls.parse(raw_file.raw_content, raw_file.filename)
    for t in trades:
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
    db.commit()

    return ImportResponse(imported_count=len(trades))


@router.delete("/trades", status_code=status.HTTP_200_OK)
def clear_trades(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete all trades for the current user. Raw files, analyses, and reports are preserved for admin retrieval."""
    user_id = current_user.id
    db.query(Trade).filter(
        Trade.user_id == user_id, Trade.is_deleted.is_(False)
    ).update({"is_deleted": True}, synchronize_session=False)
    # Clear stats snapshots since the underlying data has changed
    db.query(Analysis).filter(Analysis.user_id == user_id).update(
        {"stats_snapshot": None}, synchronize_session=False
    )
    db.commit()
    return {"detail": "ok"}
