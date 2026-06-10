"""Tests for FIFO position builder engine."""
from dataclasses import dataclass
from datetime import date, datetime

from app.engine.position import PositionBuilder, PositionResult


@dataclass
class _Trade:
    """Minimal trade-like object for testing."""

    id: str
    symbol: str
    asset_type: str
    datetime: datetime
    side: str
    quantity: float
    price: float


class TestSimpleBuySell:
    """1 BUY + 1 SELL -> 1 position with correct pnl."""

    def test_creates_one_position(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 100, 10.0,
            ),
            _Trade(
                "t2", "000001", "stock",
                datetime(2024, 1, 10, 14, 0), "SELL", 100, 12.0,
            ),
        ]
        positions = PositionBuilder.build(trades)
        assert len(positions) == 1

    def test_position_fields_are_correct(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 100, 10.0,
            ),
            _Trade(
                "t2", "000001", "stock",
                datetime(2024, 1, 10, 14, 0), "SELL", 100, 12.0,
            ),
        ]
        p = PositionBuilder.build(trades)[0]

        assert p.symbol == "000001"
        assert p.asset_type == "stock"
        assert p.total_quantity == 100
        assert p.avg_entry_price == 10.0
        assert p.avg_exit_price == 12.0
        assert p.pnl == 200.0  # (12 - 10) * 100
        assert p.pnl_pct == 0.2
        assert p.entry_date == date(2024, 1, 2)
        assert p.exit_date == date(2024, 1, 10)
        assert p.holding_days == 8
        assert set(p.trade_ids) == {"t1", "t2"}


class TestPartialSellFifo:
    """200 BUY + 100 SELL + 100 SELL -> 2 positions via FIFO."""

    def test_two_positions_created(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 200, 10.0,
            ),
            _Trade(
                "t2", "000001", "stock",
                datetime(2024, 1, 5, 10, 0), "SELL", 100, 11.0,
            ),
            _Trade(
                "t3", "000001", "stock",
                datetime(2024, 1, 8, 14, 0), "SELL", 100, 12.0,
            ),
        ]
        positions = PositionBuilder.build(trades)
        assert len(positions) == 2

    def test_first_partial_position(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 200, 10.0,
            ),
            _Trade(
                "t2", "000001", "stock",
                datetime(2024, 1, 5, 10, 0), "SELL", 100, 11.0,
            ),
            _Trade(
                "t3", "000001", "stock",
                datetime(2024, 1, 8, 14, 0), "SELL", 100, 12.0,
            ),
        ]
        p1 = PositionBuilder.build(trades)[0]

        assert p1.total_quantity == 100
        assert p1.avg_entry_price == 10.0
        assert p1.avg_exit_price == 11.0
        assert p1.pnl == 100.0  # (11 - 10) * 100
        assert p1.entry_date == date(2024, 1, 2)
        assert p1.exit_date == date(2024, 1, 5)
        assert p1.holding_days == 3
        assert set(p1.trade_ids) == {"t1", "t2"}

    def test_second_partial_position(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 200, 10.0,
            ),
            _Trade(
                "t2", "000001", "stock",
                datetime(2024, 1, 5, 10, 0), "SELL", 100, 11.0,
            ),
            _Trade(
                "t3", "000001", "stock",
                datetime(2024, 1, 8, 14, 0), "SELL", 100, 12.0,
            ),
        ]
        p2 = PositionBuilder.build(trades)[1]

        assert p2.total_quantity == 100
        assert p2.avg_entry_price == 10.0
        assert p2.avg_exit_price == 12.0
        assert p2.pnl == 200.0  # (12 - 10) * 100
        assert p2.entry_date == date(2024, 1, 2)
        assert p2.exit_date == date(2024, 1, 8)
        assert p2.holding_days == 6
        assert set(p2.trade_ids) == {"t1", "t3"}


class TestMultipleSymbols:
    """2 different stocks -> 2 independent positions."""

    def test_two_independent_positions(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 100, 10.0,
            ),
            _Trade(
                "t2", "000002", "stock",
                datetime(2024, 1, 2, 9, 31), "BUY", 200, 20.0,
            ),
            _Trade(
                "t3", "000001", "stock",
                datetime(2024, 1, 10, 14, 0), "SELL", 100, 12.0,
            ),
            _Trade(
                "t4", "000002", "stock",
                datetime(2024, 1, 15, 14, 0), "SELL", 200, 22.0,
            ),
        ]
        positions = PositionBuilder.build(trades)

        assert len(positions) == 2
        symbols = {p.symbol for p in positions}
        assert symbols == {"000001", "000002"}

    def test_correct_pnl_per_symbol(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 100, 10.0,
            ),
            _Trade(
                "t2", "000002", "stock",
                datetime(2024, 1, 2, 9, 31), "BUY", 200, 20.0,
            ),
            _Trade(
                "t3", "000001", "stock",
                datetime(2024, 1, 10, 14, 0), "SELL", 100, 12.0,
            ),
            _Trade(
                "t4", "000002", "stock",
                datetime(2024, 1, 15, 14, 0), "SELL", 200, 22.0,
            ),
        ]
        positions = PositionBuilder.build(trades)
        by_symbol = {p.symbol: p for p in positions}

        assert by_symbol["000001"].pnl == 200.0
        assert by_symbol["000002"].pnl == 400.0


class TestNoSellNoPosition:
    """Only BUY trades, no closed positions created."""

    def test_buys_only_returns_empty(self):
        trades = [
            _Trade(
                "t1", "000001", "stock",
                datetime(2024, 1, 2, 9, 30), "BUY", 100, 10.0,
            ),
            _Trade(
                "t2", "000002", "stock",
                datetime(2024, 1, 2, 9, 31), "BUY", 200, 20.0,
            ),
        ]
        positions = PositionBuilder.build(trades)
        assert len(positions) == 0

    def test_empty_trades_returns_empty(self):
        positions = PositionBuilder.build([])
        assert len(positions) == 0
