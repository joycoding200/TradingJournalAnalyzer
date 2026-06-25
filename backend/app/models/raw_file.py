"""RawFile model — stores file metadata, content lives on disk under uploads/."""
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class RawFile(Base):
    __tablename__ = "raw_files"

    __table_args__ = (
        sa.Index("ix_raw_files_user_content_hash", "user_id", "content_hash"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename = Column(String(500), nullable=False)
    source_type = Column(String(50), nullable=True)
    asset_type = Column(String(20), nullable=True)
    file_path = Column(String(1000), nullable=True)  # rel path under backend/uploads/
    file_size = Column(Integer, nullable=True)         # bytes
    content_hash = Column(String(64), nullable=True)  # SHA256 hex digest
    uploaded_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now()
    )
