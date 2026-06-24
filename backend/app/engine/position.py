"""FIFO position builder engine.

Transforms raw trade records into closed positions using
FIFO (First-In-First-Out) matching. Each sell matches against
the oldest unmatched buy lots.

Orphan sells (no prior buy in the data) are treated as positions
with unknown cost basis, using the sell price as entry price.
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
    cost_known: bool = True  # False if entry price is estimated (pre-existing position)
    entry_count: int = 0  # Number of buy batches (P0-1 grouped)
    total_buys: float = 0.0  # Total buy quantity (P0-1 grouped)
    total_sells: float = 0.0  # Total sell quantity (P0-1 grouped)
    # Total commissions (buy + sell) the position actually incurred. `pnl`
    # above already has these subtracted; exposed separately so counterfactual
    # backtests (e.g. stop-loss) can keep the same fee basis. See P1b.
    total_commission: float = 0.0


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
        """Build positions for a single symbol using FIFO lot matching.

        Orphan sells (no prior buy) indicate pre-existing positions from
        before the data start date. These are treated as positions with
        unknown cost basis: the entry price is set equal to the sell price
        (PnL = 0), and cost_known = False.
        """
        positions: list[PositionResult] = []
        long_queue: deque = deque()

        for trade in trades:
            trade_comm = getattr(trade, 'commission', 0) or 0
            if trade.side == "BUY":
                long_queue.append(
                    (trade.quantity, trade.price, trade.id, trade.datetime, trade_comm)
                )
            else:
                remaining = trade.quantity
                sell_trade_ids = [trade.id]
                total_cost = 0.0
                total_qty = 0.0
                total_buy_comm = 0.0  # Accumulated buy-side fees
                entry_date: date | None = None

                while remaining > 0 and long_queue:
                    buy_qty, buy_price, buy_id, buy_dt, bc = long_queue[0]
                    if entry_date is None:
                        entry_date = buy_dt.date()

                    matched = min(remaining, buy_qty)
                    total_cost += matched * buy_price
                    total_buy_comm += (matched / buy_qty) * bc if buy_qty > 0 else 0
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
                            bc * (1 - matched / buy_qty),
                        )

                # Handle orphan sell: pre-existing position with unknown cost
                if total_qty == 0 and remaining > 0:
                    # Use sell price as entry price — cost basis unknown
                    orphan_qty = remaining
                    positions.append(
                        PositionResult(
                            symbol=symbol,
                            asset_type=trade.asset_type,
                            entry_date=trade.datetime.date(),  # unknown, use exit date
                            exit_date=trade.datetime.date(),
                            holding_days=1,
                            total_quantity=orphan_qty,
                            avg_entry_price=trade.price,  # unknown cost basis
                            avg_exit_price=trade.price,
                            pnl=0.0,
                            pnl_pct=0.0,
                            trade_ids=[trade.id],
                            cost_known=False,
                        )
                    )

                if total_qty > 0:
                    avg_entry = total_cost / total_qty
                    # PnL = sell proceeds - buy cost - all fees
                    # Pro-rate sell commission if we only matched part of the sell
                    if trade.quantity > 0:
                        sell_comm = trade_comm * (total_qty / trade.quantity)
                    else:
                        sell_comm = 0.0
                    pnl = (trade.price - avg_entry) * total_qty - total_buy_comm - sell_comm
                    pnl_pct = (
                        pnl / (avg_entry * total_qty + total_buy_comm)
                        if avg_entry != 0 and total_qty != 0
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
                            cost_known=True,
                            total_commission=round(total_buy_comm + sell_comm, 2),
                        )
                    )

                # Handle orphan remaining quantity (partial orphan)
                if total_qty > 0 and remaining > 0:
                    # Use sell price as entry price for orphan portion
                    positions.append(
                        PositionResult(
                            symbol=symbol,
                            asset_type=trade.asset_type,
                            entry_date=trade.datetime.date(),
                            exit_date=trade.datetime.date(),
                            holding_days=1,
                            total_quantity=remaining,
                            avg_entry_price=trade.price,
                            avg_exit_price=trade.price,
                            pnl=0.0,
                            pnl_pct=0.0,
                            trade_ids=[trade.id],
                            cost_known=False,
                        )
                    )

        return positions

    # ------------------------------------------------------------------
    # P0-1: Group-based reconstruction (PRD-compliant)
    # ------------------------------------------------------------------

    @staticmethod
    def build_grouped(trades) -> list[PositionResult]:
        """Group-based reconstruction: merge consecutive same-symbol trades.

        Unlike build() (the default FIFO method used by the API), this method
        groups consecutive buys and sells for the same symbol into unified
        positions when cumulative sells >= cumulative buys. Weighted average
        prices are used for both entry and exit.

        This method is retained because:
        - Golden tests (tests/golden/) compare against build_grouped output
        - It handles pre-existing positions correctly (orphan sells from before
          the statement start date), which FIFO build() discards
        - It serves as a reference implementation for the PRD-specified behavior

        For API usage (analysis.py), use build() (FIFO) — that is the primary
        production code path and what stats/insight/whatif endpoints consume.

        Args:
            trades: Iterable of objects with attributes:
                symbol, asset_type, datetime, side, quantity, price, id.

        Returns:
            List of PositionResult with merged trades.
        """
        by_symbol: dict[str, list] = {}
        for t in trades:
            by_symbol.setdefault(t.symbol, []).append(t)

        positions: list[PositionResult] = []
        for symbol, symbol_trades in by_symbol.items():
            sorted_trades = sorted(symbol_trades, key=lambda t: t.datetime)
            positions.extend(
                PositionBuilder._group_for_symbol(symbol, sorted_trades)
            )
        return positions

    @staticmethod
    def _group_for_symbol(symbol: str, trades) -> list[PositionResult]:
        """Build grouped positions for a single symbol.

        Merges consecutive trades into one position when cumulative
        sells >= cumulative buys. Handles orphan sells (no prior buy)
        as positions with unknown cost basis.
        """
        positions: list[PositionResult] = []
        buy_batches: list = []  # (qty, price, id, dt, comm)
        sell_batches: list = []  # (qty, price, id, dt, comm)
        cum_buys = 0.0
        cum_sells = 0.0

        for trade in trades:
            trade_comm = getattr(trade, 'commission', 0) or 0
            if trade.side == "BUY":
                buy_batches.append(
                    (trade.quantity, trade.price, trade.id, trade.datetime, trade_comm)
                )
                cum_buys += trade.quantity
            else:  # SELL
                sell_batches.append(
                    (trade.quantity, trade.price, trade.id, trade.datetime, trade_comm)
                )
                cum_sells += trade.quantity

            # Orphan sell: sell with no prior buys
            if cum_sells > 0 and cum_buys == 0:
                orphan_qty = cum_sells
                last_sell_price = sell_batches[-1][1]
                all_ids = [s[2] for s in sell_batches]
                first_dt = sell_batches[0][3]
                last_dt = sell_batches[-1][3]
                positions.append(
                    PositionResult(
                        symbol=symbol,
                        asset_type=trade.asset_type,
                        entry_date=first_dt.date(),
                        exit_date=last_dt.date(),
                        holding_days=max((last_dt.date() - first_dt.date()).days, 1),
                        total_quantity=orphan_qty,
                        avg_entry_price=last_sell_price,
                        avg_exit_price=last_sell_price,
                        pnl=0.0,
                        pnl_pct=0.0,
                        trade_ids=all_ids,
                        cost_known=False,
                        total_sells=orphan_qty,
                    )
                )
                sell_batches = []
                cum_sells = 0
                continue

            # When sells >= buys (and there were buys), close the position
            if cum_sells >= cum_buys and cum_buys > 0:
                total_buy_qty = sum(b[0] for b in buy_batches)
                total_buy_cost = sum(b[0] * b[1] for b in buy_batches)
                total_buy_comm = sum(b[4] for b in buy_batches)
                avg_entry = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0.0

                # Match sells against buys proportionally
                matched_sell_qty = 0.0
                matched_sell_revenue = 0.0
                matched_sell_comm = 0.0
                remaining = cum_buys
                for s in sell_batches:
                    take = min(s[0], remaining)
                    ratio = take / s[0] if s[0] > 0 else 0
                    matched_sell_qty += take
                    matched_sell_revenue += take * s[1]
                    matched_sell_comm += ratio * s[4]
                    remaining -= take
                    if remaining <= 0:
                        break

                avg_exit = matched_sell_revenue / matched_sell_qty if matched_sell_qty > 0 else 0.0
                # PnL = sell proceeds - buy cost - all fees
                total_commission = total_buy_comm + matched_sell_comm
                pnl = matched_sell_revenue - total_buy_cost - total_commission

                entry_date = buy_batches[0][3].date()
                exit_date = sell_batches[-1][3].date()  # last sell date = full exit

                all_ids = [b[2] for b in buy_batches] + [s[2] for s in sell_batches]

                excess = cum_sells - cum_buys
                num_buys = len(buy_batches)
                invested = total_buy_cost + total_buy_comm

                positions.append(
                    PositionResult(
                        symbol=symbol,
                        asset_type=trade.asset_type,
                        entry_date=entry_date,
                        exit_date=exit_date,
                        holding_days=max((exit_date - entry_date).days, 1),
                        total_quantity=total_buy_qty,
                        avg_entry_price=round(avg_entry, 4),
                        avg_exit_price=round(avg_exit, 4),
                        pnl=round(pnl, 2),
                        pnl_pct=round(pnl / invested, 4) if invested > 0 else 0.0,
                        trade_ids=all_ids,
                        cost_known=True,
                        entry_count=num_buys,
                        total_buys=cum_buys,
                        total_sells=cum_sells,
                        total_commission=round(total_commission, 2),
                    )
                )

                # Reset for next cycle, carry over excess sells
                buy_batches = []
                cum_buys = 0

                if excess > 0:
                    remaining_excess = excess
                    new_sell_batches = []
                    for s in reversed(sell_batches):
                        if remaining_excess > 0:
                            take = min(s[0], remaining_excess)
                            ratio = take / s[0] if s[0] > 0 else 0
                            new_sell_batches.insert(0, (take, s[1], s[2], s[3], ratio * s[4]))
                            remaining_excess -= take
                    sell_batches = new_sell_batches
                    cum_sells = excess
                else:
                    sell_batches = []
                    cum_sells = 0

        return positions
