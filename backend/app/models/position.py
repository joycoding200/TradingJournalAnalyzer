"""Position model."""
from uuid import uuid4

from sqlalchemy import Column, Date, Float, ForeignKey, Index, Integer, String, JSON

from app.database import Base


class Position(Base):
    __tablename__ = "positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol = Column(String(20), nullable=False)
    asset_type = Column(String(10), nullable=False)
    entry_date = Column(Date, nullable=False)
    exit_date = Column(Date, nullable=False)
    holding_days = Column(Integer, nullable=False)
    total_quantity = Column(Float, nullable=False)
    avg_entry_price = Column(Float, nullable=False)
    avg_exit_price = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    trade_ids = Column(JSON, nullable=False)

    __table_args__ = (
        Index("ix_positions_user_entry_date", "user_id", "entry_date"),
        Index("ix_positions_symbol", "symbol"),
    )
