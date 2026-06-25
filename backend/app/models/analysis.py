"""Analysis model."""
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, JSON

from app.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_file_id = Column(
        String(36), ForeignKey("raw_files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    date_start = Column(Date, nullable=False)
    date_end = Column(Date, nullable=False)
    stats_snapshot = Column(JSON, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now()
    )

    __table_args__ = (
        Index("ix_analyses_user_date_range", "user_id", "date_start", "date_end"),
    )


class AnalysisFile(Base):
    """Many-to-many association between Analysis and RawFile.

    Allows one analysis to span multiple uploaded trading statements,
    which is necessary because Chinese brokerages limit export date ranges
    (typically 3 months per file).
    """
    __tablename__ = "analysis_files"

    analysis_id = Column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True
    )
    raw_file_id = Column(
        String(36), ForeignKey("raw_files.id", ondelete="CASCADE"), primary_key=True
    )
