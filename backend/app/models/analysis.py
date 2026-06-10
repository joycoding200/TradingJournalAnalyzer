"""Analysis model."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, Date, DateTime, ForeignKey, String

from app.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    date_start = Column(Date, nullable=False)
    date_end = Column(Date, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
