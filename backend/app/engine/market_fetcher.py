"""Market data fetcher — pull A-share daily bars via mootdx (TDX TCP), cache to DailyBar.

Data source priority: mootdx (TCP 7709, no IP blocking) → skip market patterns gracefully.

Usage:
    from app.engine.market_fetcher import ensure_market_data

    # Fetch and cache bars, returns data dict for PatternEngine
    data = ensure_market_data(db, ["600036", "000858"], start, end)
"""

from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.engine.market_data import MarketDataCache

# Module-level client — TCP connection reused across symbols
_CLIENT = None
_PAGE_SIZE = 800


def _get_client():
    """Return a cached mootdx Quotes client for standard market."""
    global _CLIENT
    if _CLIENT is None:
        from mootdx.quotes import Quotes
        from mootdx.consts import KLINE_DAILY
        _CLIENT = Quotes.factory(market='std', timeout=15)
    return _CLIENT


def _compute_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Add MA5, MA10, MA20, MA60, avg_volume_20d columns."""
    df = df.sort_values("date")
    df["ma5"] = df["close"].rolling(5, min_periods=1).mean().round(4)
    df["ma10"] = df["close"].rolling(10, min_periods=1).mean().round(4)
    df["ma20"] = df["close"].rolling(20, min_periods=1).mean().round(4)
    df["ma60"] = df["close"].rolling(60, min_periods=1).mean().round(4)
    df["avg_volume_20d"] = df["volume"].rolling(20, min_periods=1).mean().round(2)
    return df


def _fetch_single_symbol(db: Session, symbol: str) -> int:
    """Fetch all history for one symbol via mootdx. Returns count of new bars stored."""
    from mootdx.consts import KLINE_DAILY

    client = _get_client()

    # Paginate through all available history
    all_frames = []
    start = 0
    while True:
        try:
            chunk = client.bars(
                symbol=symbol,
                frequency=KLINE_DAILY,
                start=start,
                offset=_PAGE_SIZE,
            )
        except Exception:
            break

        if chunk is None or chunk.empty:
            break

        all_frames.append(chunk)
        if len(chunk) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE

    if not all_frames:
        return 0

    raw = pd.concat(all_frames, ignore_index=False)
    raw = raw[~raw.index.duplicated(keep='first')]

    # Normalize columns to match DailyBar schema
    if 'datetime' in raw.columns:
        raw['date'] = pd.to_datetime(raw['datetime']).dt.date
    else:
        raw['date'] = raw.index.to_series().dt.date

    raw['symbol'] = symbol
    raw['volume'] = raw.get('vol', raw.get('volume', 0))

    # Rename columns to expected format
    col_map = {}
    for c in ['open', 'high', 'low', 'close', 'amount']:
        if c in raw.columns:
            col_map[c] = c
    raw = raw.rename(columns=col_map)

    # Compute MAs over full history
    raw = _compute_moving_averages(raw)

    # Find dates not already cached
    existing_dates: set[date] = set()
    try:
        bars = MarketDataCache.get_bars(
            db, symbol, raw["date"].min(), raw["date"].max()
        )
        existing_dates = {date.fromisoformat(b["date"]) for b in bars}
    except Exception:
        pass

    new_rows = [
        r for _, r in raw.iterrows()
        if r["date"] not in existing_dates
    ]
    if not new_rows:
        return 0

    stored = MarketDataCache.store_bars(
        db,
        [
            {
                "symbol": symbol,
                "date": row["date"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0) or 0.0),
                "ma5": float(row["ma5"]) if pd.notna(row.get("ma5")) else None,
                "ma10": float(row["ma10"]) if pd.notna(row.get("ma10")) else None,
                "ma20": float(row["ma20"]) if pd.notna(row.get("ma20")) else None,
                "ma60": float(row["ma60"]) if pd.notna(row.get("ma60")) else None,
                "avg_volume_20d": (
                    float(row["avg_volume_20d"])
                    if pd.notna(row.get("avg_volume_20d"))
                    else None
                ),
            }
            for row in new_rows
        ],
    )
    return stored


def ensure_market_data(
    db: Session, symbols: list[str], start: date, end: date
) -> dict:
    """Fetch and cache daily bars for given symbols, then return market_data dict.

    Fetches from 120 calendar days before `start` to ensure MAs are accurate.

    Returns dict in PatternEngine format:
        {symbol: {date_str: {open, high, low, close, volume, ma5, ...}}}
    """
    if not symbols:
        return {}

    lookback_start = start - timedelta(days=120)

    for sym in set(symbols):
        _fetch_single_symbol(db, sym)

    return MarketDataCache.get_market_data(
        db, list(set(symbols)), lookback_start, end
    )
