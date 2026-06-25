"""Market data cache engine -- load/store daily bars."""
from datetime import date
from sqlalchemy.orm import Session
from app.models.daily_bar import DailyBar


class MarketDataCache:
    """Cache and retrieve daily OHLCV bar data for pattern tagging."""

    @staticmethod
    def get_bars(db: Session, symbol: str, start: date, end: date) -> list[dict]:
        """Get daily bars for a symbol within a date range, ordered by date."""
        bars = (
            db.query(DailyBar)
            .filter(
                DailyBar.symbol == symbol,
                DailyBar.date >= start,
                DailyBar.date <= end,
            )
            .order_by(DailyBar.date)
            .all()
        )
        return [
            {
                "date": str(b.date),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "ma5": b.ma5,
                "ma10": b.ma10,
                "ma20": b.ma20,
                "ma60": b.ma60,
                "avg_volume_20d": b.avg_volume_20d,
            }
            for b in bars
        ]

    @staticmethod
    def get_market_data(
        db: Session, symbols: list[str], start: date, end: date
    ) -> dict:
        """Build the nested dict expected by PatternEngine.tag_market_patterns().

        Returns:
            {symbol: {date_str: {open, high, low, close, volume, ma5, ...}}}
        """
        result: dict[str, dict[str, dict]] = {}
        for symbol in symbols:
            bars = MarketDataCache.get_bars(db, symbol, start, end)
            symbol_data = {}
            for b in bars:
                symbol_data[b["date"]] = {
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                    "ma5": b["ma5"],
                    "ma10": b["ma10"],
                    "ma20": b["ma20"],
                    "ma60": b["ma60"],
                    "avg_volume_20d": b["avg_volume_20d"],
                }
            result[symbol] = symbol_data
        return result

    @staticmethod
    def store_bars(db: Session, bars: list[dict]) -> int:
        """Store daily bars, skipping duplicates via the UNIQUE constraint.

        On PostgreSQL: uses ON CONFLICT DO NOTHING — atomic across
        concurrent workers with no extra round-trip.

        On SQLite: falls back to check-then-insert (no concurrent writers
        in SQLite, so the race is harmless).
        """
        if not bars:
            return 0

        engine = db.get_bind()
        is_postgres = engine.dialect.name == "postgresql"

        if is_postgres:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(DailyBar).values(
                [
                    {
                        "symbol": b["symbol"],
                        "date": b["date"],
                        "open": b["open"],
                        "high": b["high"],
                        "low": b["low"],
                        "close": b["close"],
                        "volume": b.get("volume", 0.0),
                        "ma5": b.get("ma5"),
                        "ma10": b.get("ma10"),
                        "ma20": b.get("ma20"),
                        "ma60": b.get("ma60"),
                        "avg_volume_20d": b.get("avg_volume_20d"),
                    }
                    for b in bars
                ]
            ).on_conflict_do_nothing(index_elements=["symbol", "date"])

            result = db.execute(stmt)
            db.commit()
            return result.rowcount if result.rowcount else 0

        # SQLite / other: batch-insert, skipping existing dates
        symbol = bars[0]["symbol"]
        dates = [b["date"] for b in bars]
        existing = set(
            db.query(DailyBar.date)
            .filter(DailyBar.symbol == symbol, DailyBar.date.in_(dates))
            .all()
        )
        existing_dates = {d[0] for d in existing}

        count = 0
        for b in bars:
            if b["date"] not in existing_dates:
                db.add(
                    DailyBar(
                        symbol=b["symbol"],
                        date=b["date"],
                        open=b["open"],
                        high=b["high"],
                        low=b["low"],
                        close=b["close"],
                        volume=b.get("volume", 0.0),
                        ma5=b.get("ma5"),
                        ma10=b.get("ma10"),
                        ma20=b.get("ma20"),
                        ma60=b.get("ma60"),
                        avg_volume_20d=b.get("avg_volume_20d"),
                    )
                )
                count += 1
        db.commit()
        return count
