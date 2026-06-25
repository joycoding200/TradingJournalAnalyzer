"""Pattern model."""
from uuid import uuid4

from sqlalchemy import Column, Float, ForeignKey, String, JSON

from app.database import Base


class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    position_id = Column(
        String(36), ForeignKey("positions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pattern_name = Column(String(30), nullable=False, index=True)
    confidence = Column(Float, default=1.0)
    context = Column(JSON, default=dict)
