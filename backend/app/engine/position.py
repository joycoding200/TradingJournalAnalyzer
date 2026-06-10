"""FIFO position builder engine.

Transforms raw trade records into closed positions using
FIFO (First-In-First-Out) matching. Each sell matches against
the oldest unmatched buy lots.
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import date


@dataclass
class PositionResult:
    """A fully closed position reconstructed from trade records."""

    symbol: str
    asset_type: str
    entry_date: date
    exit_date: date
    holding_days: int
    total_quantity: float
    avg_entry_price: float
    avg_exit_price: float
    pnl: float
    pnl_pct: float
    trade_ids: list[str] = field(default_factory=list)


class PositionBuilder:
    """Reconstruct closed positions from raw trades using FIFO matching."""

    @staticmethod
    def build(trades) -> list[PositionResult]:
        """Build positions from a list of trade-like objects.

        Args:
            trades: Iterable of objects with attributes:
                symbol, asset_type, datetime, side, quantity, price, id.

        Returns:
            List of PositionResult for each fully closed position.
        """
        by_symbol: dict[str, list] = {}
        for t in trades:
            by_symbol.setdefault(t.symbol, []).append(t)

        positions: list[PositionResult] = []
        for symbol, symbol_trades in by_symbol.items():
            sorted_trades = sorted(symbol_trades, key=lambda t: t.datetime)
            positions.extend(
                PositionBuilder._build_for_symbol(symbol, sorted_trades)
            )
        return positions

    @staticmethod
    def _build_for_symbol(symbol: str, trades) -> list[PositionResult]:
        """Build positions for a single symbol using FIFO lot matching."""
        positions: list[PositionResult] = []
        long_queue: deque = deque()

        for trade in trades:
            if trade.side == "BUY":
                long_queue.append(
                    (trade.quantity, trade.price, trade.id, trade.datetime)
                )
            else:
                remaining = trade.quantity
                sell_trade_ids = [trade.id]
                total_cost = 0.0
                total_qty = 0.0
                entry_date: date | None = None

                while remaining > 0 and long_queue:
                    buy_qty, buy_price, buy_id, buy_dt = long_queue[0]
                    if entry_date is None:
                        entry_date = buy_dt.date()

                    matched = min(remaining, buy_qty)
                    total_cost += matched * buy_price
                    total_qty += matched
                    sell_trade_ids.append(buy_id)
                    remaining -= matched

                    if matched >= buy_qty:
                        long_queue.popleft()
                    else:
                        long_queue[0] = (
                            buy_qty - matched,
                            buy_price,
                            buy_id,
                            buy_dt,
                        )

                if total_qty > 0:
                    avg_entry = total_cost / total_qty
                    pnl = (trade.price - avg_entry) * total_qty
                    pnl_pct = (
                        (trade.price - avg_entry) / avg_entry
                        if avg_entry != 0
                        else 0.0
                    )
                    exit_date = trade.datetime.date()
                    entry = entry_date or date.today()
                    positions.append(
                        PositionResult(
                            symbol=symbol,
                            asset_type=trade.asset_type,
                            entry_date=entry,
                            exit_date=exit_date,
                            holding_days=max(
                                (exit_date - entry).days, 1
                            ),
                            total_quantity=total_qty,
                            avg_entry_price=avg_entry,
                            avg_exit_price=trade.price,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            trade_ids=sell_trade_ids,
                        )
                    )

        return positions
