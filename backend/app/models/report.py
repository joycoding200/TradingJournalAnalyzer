"""Report model."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, JSON

from app.database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    analysis_input = Column(JSON, nullable=False)
    ai_provider = Column(String(20), nullable=False)
    report_content = Column(Text, nullable=False)
    validation_passed = Column(Boolean, default=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
