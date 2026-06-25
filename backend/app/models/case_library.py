"""CaseLibrary model for anonymous case contribution."""
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.database import Base


class CaseLibrary(Base):
    __tablename__ = "case_library"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id = Column(
        String(36), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    trades_json = Column(Text, nullable=False)
    positions_json = Column(Text, nullable=False)
    stats_json = Column(Text, nullable=False)
    patterns_json = Column(Text, nullable=True)
    report_content = Column(Text, nullable=True)
    raw_file_content = Column(Text, nullable=False)
    raw_filename = Column(String(500), nullable=False)
    contributed_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now()
    )
