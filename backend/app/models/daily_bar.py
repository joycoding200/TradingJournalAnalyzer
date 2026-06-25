"""Daily OHLCV bar model for caching market data."""
import uuid
from datetime import date, datetime, timezone
import sqlalchemy as sa
from sqlalchemy import String, Date, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DailyBar(Base):
    __tablename__ = "daily_bars"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ma5: Mapped[float] = mapped_column(Float, nullable=True)
    ma10: Mapped[float] = mapped_column(Float, nullable=True)
    ma20: Mapped[float] = mapped_column(Float, nullable=True)
    ma60: Mapped[float] = mapped_column(Float, nullable=True)
    avg_volume_20d: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now()
    )

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_daily_bar_symbol_date"),
    )
