"""MAE/MFE computation — Maximum Adverse/Favorable Excursion.

Computes the worst/best percentage drawdown from entry price during
a position's lifetime, using daily bar low/high data.

MAE (Maximum Adverse Excursion):
    The largest percentage loss from entry price during the holding period.
    Based on daily low relative to avg_entry_price.

MFE (Maximum Favorable Excursion):
    The largest percentage gain from entry price during the holding period.
    Based on daily high relative to avg_entry_price.
"""

from datetime import date


def compute_mae_mfe(pos, market_data: dict) -> dict:
    """Compute MAE/MFE for a single position.

    Iterates daily bars from entry_date to exit_date, tracking
    the lowest low (for MAE) and highest high (for MFE).

    Args:
        pos: Position-like object with symbol, entry_date, exit_date, avg_entry_price.
        market_data: {symbol: {date_str: {high, low}}}.

    Returns:
        dict with keys: mae_pct, mfe_pct, mae_price, mfe_price.
        All values are 0.0 if market_data is unavailable for the symbol.
    """
    symbol_data = market_data.get(pos.symbol)
    if not symbol_data:
        return {"mae_pct": 0.0, "mfe_pct": 0.0, "mae_price": 0.0, "mfe_price": 0.0}

    entry_price = pos.avg_entry_price
    if entry_price <= 0:
        return {"mae_pct": 0.0, "mfe_pct": 0.0, "mae_price": 0.0, "mfe_price": 0.0}

    mae_pct = 0.0   # most negative % from entry (<= 0)
    mfe_pct = 0.0   # most positive % from entry (>= 0)
    mae_price = entry_price
    mfe_price = entry_price

    for date_str in sorted(symbol_data):
        bar_date = date.fromisoformat(date_str)
        if pos.entry_date <= bar_date <= pos.exit_date:
            bar = symbol_data[date_str]
            bar_low = bar.get("low", entry_price)
            bar_high = bar.get("high", entry_price)

            daily_mae = (bar_low - entry_price) / entry_price
            daily_mfe = (bar_high - entry_price) / entry_price

            if daily_mae < mae_pct:
                mae_pct = daily_mae
                mae_price = bar_low
            if daily_mfe > mfe_pct:
                mfe_pct = daily_mfe
                mfe_price = bar_high

    return {
        "mae_pct": round(mae_pct, 4),
        "mfe_pct": round(mfe_pct, 4),
        "mae_price": round(mae_price, 4),
        "mfe_price": round(mfe_price, 4),
    }


def compute_mae_mfe_stats(positions: list, market_data: dict) -> dict:
    """Aggregate MAE/MFE statistics across all positions.

    Returns:
        dict with: avg_mae, avg_mfe, mae_winners, mae_losers,
        mfe_winners, mfe_losers, profit_capture_ratio.
    """
    results = []
    for p in positions:
        m = compute_mae_mfe(p, market_data)
        m["pnl_pct"] = p.pnl_pct
        m["is_win"] = p.pnl > 0
        results.append(m)

    if not results:
        return {
            "avg_mae": 0.0, "avg_mfe": 0.0,
            "mae_winners": 0.0, "mae_losers": 0.0,
            "mfe_winners": 0.0, "mfe_losers": 0.0,
            "profit_capture_ratio": 0.0,
        }

    winners = [r for r in results if r["is_win"]]
    losers = [r for r in results if not r["is_win"]]

    avg_mae = sum(r["mae_pct"] for r in results) / len(results)
    avg_mfe = sum(r["mfe_pct"] for r in results) / len(results)

    mae_winners = sum(r["mae_pct"] for r in winners) / len(winners) if winners else 0.0
    mae_losers = sum(r["mae_pct"] for r in losers) / len(losers) if losers else 0.0
    mfe_winners = sum(r["mfe_pct"] for r in winners) / len(winners) if winners else 0.0
    mfe_losers = sum(r["mfe_pct"] for r in losers) / len(losers) if losers else 0.0

    # Profit capture: per-position mean of capture ratios
    # Using mean(capture_i) instead of sum(pnl)/sum(mfe) avoids
    # bias where one trade with huge MFE dominates the aggregate.
    captures = [
        r["pnl_pct"] / r["mfe_pct"]
        for r in winners if r["mfe_pct"] > 0.001  # filter out negligible MFE to avoid distortion
    ]
    profit_capture = sum(captures) / len(captures) if captures else 0.0

    return {
        "avg_mae": round(avg_mae, 4),
        "avg_mfe": round(avg_mfe, 4),
        "mae_winners": round(mae_winners, 4),
        "mae_losers": round(mae_losers, 4),
        "mfe_winners": round(mfe_winners, 4),
        "mfe_losers": round(mfe_losers, 4),
        "profit_capture_ratio": round(profit_capture, 4),
    }
