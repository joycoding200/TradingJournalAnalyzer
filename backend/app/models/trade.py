"""Trade model."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String

from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    raw_file_id = Column(
        String(36), ForeignKey("raw_files.id"), nullable=False
    )
    user_id = Column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    asset_type = Column(String(10), nullable=False)
    datetime = Column(DateTime, nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    side = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    margin = Column(Float, nullable=True)
    multiplier = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_trades_user_datetime", "user_id", "datetime"),
        Index(
            "ix_trades_user_symbol_datetime",
            "user_id",
            "symbol",
            "datetime",
        ),
    )
