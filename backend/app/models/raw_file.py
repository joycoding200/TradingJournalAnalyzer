"""RawFile model."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, LargeBinary, String

from app.database import Base


class RawFile(Base):
    __tablename__ = "raw_files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    filename = Column(String(500), nullable=False)
    source_type = Column(String(50), nullable=True)
    asset_type = Column(String(20), nullable=True)
    raw_content = Column(LargeBinary, nullable=False)
    uploaded_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
