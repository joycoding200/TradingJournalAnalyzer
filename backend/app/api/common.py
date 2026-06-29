"""Common functions shared between API modules."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.analysis import Analysis, AnalysisFile
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


def get_raw_file_ids(analysis_id: str, db: Session) -> list[str]:
    """Return all RawFile IDs linked to an analysis via the association table.

    Falls back to the legacy Analysis.raw_file_id column for analyses
    created before the multi-file feature was added.
    """
    rows = (
        db.query(AnalysisFile.raw_file_id)
        .filter(AnalysisFile.analysis_id == analysis_id)
        .all()
    )
    file_ids = [row[0] for row in rows]
    if not file_ids:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if analysis and analysis.raw_file_id:
            file_ids = [analysis.raw_file_id]
    return file_ids


def get_raw_file_filenames(raw_file_ids: list[str], db: Session) -> dict[str, str]:
    """Return {raw_file_id: filename} for a list of IDs."""
    from app.models.raw_file import RawFile

    filename_map: dict[str, str] = {}
    if raw_file_ids:
        rfs = db.query(RawFile).filter(RawFile.id.in_(raw_file_ids)).all()
        filename_map = {rf.id: rf.filename for rf in rfs}
    return filename_map


def build_symbol_name_map(trades: list[Trade]) -> dict[str, str]:
    """Build {symbol: Chinese name} from trade rows.

    Scans trades in reverse-chronological order and keeps the first non-empty
    name seen for each symbol. This means a later import carrying the 证券名称
    column overrides older NULL rows, while symbols whose every trade lacks a
    name (legacy imports before the symbol_name column) are simply absent.

    Shared by compute_stats (run_analysis path) and get_stats (slow path) so
    the two aggregation sites cannot drift apart — the previous duplication
    caused a bug where run_analysis wrote a name-bearing snapshot but the
    slow path recomputed a nameless one and overwrote it.
    """
    name_map: dict[str, str] = {}
    for t in sorted(trades, key=lambda x: getattr(x, "datetime", None) or "", reverse=True):
        name = getattr(t, "symbol_name", None)
        if name and t.symbol not in name_map:
            name_map[t.symbol] = name
    return name_map



def load_trades(analysis: Analysis, user_id: str, db: Session) -> list[Trade]:
    """Load the trades that belong to THIS analysis.

    An analysis can reference one or more uploaded raw files via the
    analysis_files association table. Trades are always scoped by
    raw_file_id — never by user_id + date range — to prevent
    double-counting when overlapping files are uploaded.
    """
    file_ids = get_raw_file_ids(analysis.id, db)
    if not file_ids:
        return []
    return (
        db.query(Trade)
        .filter(
            Trade.raw_file_id.in_(file_ids),
            Trade.user_id == user_id,
            Trade.is_deleted.is_(False),
        )
        .order_by(Trade.datetime)
        .all()
    )
