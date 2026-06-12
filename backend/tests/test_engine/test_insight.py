"""Tests for InsightEngine -- behavior aggregation and statistics."""
from dataclasses import dataclass, field
from datetime import date

from app.engine.insight import InsightEngine


# -- helpers ----------------------------------------------------------------


@dataclass
class _Position:
    """Minimal position-like object for testing insight."""
    symbol: str = "000001"
    asset_type: str = "stock"
    entry_date: date = date(2024, 1, 2)
    exit_date: date = date(2024, 1, 10)
    holding_days: int = 8
    total_quantity: float = 100
    avg_entry_price: float = 10.0
    avg_exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    trade_ids: list[str] = field(default_factory=lambda: ["t1"])
    cost_known: bool = True


def make_pos(pnl: float = 0.0, pnl_pct: float = 0.0) -> _Position:
    """Create a test position with given PnL values."""
    return _Position(pnl=pnl, pnl_pct=pnl_pct)


# ============================================================================
# Tests
# ============================================================================


class TestInsightEngineSingle:
    """Basic single-pattern, single-position scenarios."""

    def test_one_pattern_one_position(self):
        positions = [make_pos(pnl=100.0, pnl_pct=0.1)]
        patterns_map = {0: ["SWING"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert len(results) == 1
        item = results[0]
        assert item.pattern_name == "SWING"
        assert item.count == 1
        assert item.win_count == 1
        assert item.win_rate == 1.0
        assert item.total_pnl == 100.0
        assert item.avg_pnl_pct == 0.1
        # expectancy = 1.0 * 100.0 - 0 * 0 = 100.0
        assert item.expectancy == 100.0

    def test_multiple_positions_same_pattern(self):
        positions = [
            make_pos(pnl=100.0, pnl_pct=0.1),
            make_pos(pnl=-50.0, pnl_pct=-0.05),
            make_pos(pnl=200.0, pnl_pct=0.2),
        ]
        patterns_map = {0: ["SWING"], 1: ["SWING"], 2: ["SWING"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert len(results) == 1
        item = results[0]
        assert item.count == 3
        assert item.win_count == 2
        assert item.win_rate == 2 / 3
        assert item.total_pnl == 250.0
        expected_avg = round((0.1 + (-0.05) + 0.2) / 3, 4)
        assert item.avg_pnl_pct == expected_avg
        # expectancy = 2/3 * avg_win - 1/3 * avg_loss
        # avg_win = (100+200)/2 = 150, avg_loss = abs(-50) = 50
        # expectancy = 2/3 * 150 - 1/3 * 50 = 100 - 16.67 = 83.33
        assert round(item.expectancy, 2) == 83.33


class TestInsightEngineMultiple:
    """Multiple patterns across positions."""

    def test_multiple_patterns(self):
        positions = [
            make_pos(pnl=100.0, pnl_pct=0.1),
            make_pos(pnl=50.0, pnl_pct=0.05),
            make_pos(pnl=-30.0, pnl_pct=-0.03),
        ]
        patterns_map = {0: ["SWING"], 1: ["SWING", "TREND"], 2: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert len(results) == 3

        swing = next(r for r in results if r.pattern_name == "SWING")
        assert swing.count == 2
        assert swing.total_pnl == 150.0

        trend = next(r for r in results if r.pattern_name == "TREND")
        assert trend.count == 1
        assert trend.total_pnl == 50.0

        scalp = next(r for r in results if r.pattern_name == "SCALP")
        assert scalp.count == 1
        assert scalp.total_pnl == -30.0


class TestInsightEngineSorting:
    """Results must be sorted by total_pnl descending."""

    def test_sorted_by_total_pnl_desc(self):
        positions = [
            make_pos(pnl=100.0, pnl_pct=0.1),
            make_pos(pnl=200.0, pnl_pct=0.2),
            make_pos(pnl=50.0, pnl_pct=0.05),
        ]
        patterns_map = {0: ["A"], 1: ["B"], 2: ["C"]}
        results = InsightEngine.analyze(positions, patterns_map)
        total_pnls = [r.total_pnl for r in results]
        assert total_pnls == sorted(total_pnls, reverse=True)

    def test_negative_total_pnl_sorted_last(self):
        """Pattern with negative total_pnl should sort below positive ones."""
        positions = [
            make_pos(pnl=200.0, pnl_pct=0.2),   # A: total_pnl=200
            make_pos(pnl=-500.0, pnl_pct=-0.5),  # B: total_pnl=-500
            make_pos(pnl=50.0, pnl_pct=0.05),    # C: total_pnl=50
        ]
        patterns_map = {0: ["A"], 1: ["B"], 2: ["C"]}
        results = InsightEngine.analyze(positions, patterns_map)
        # B has negative total_pnl, should be last
        assert results[-1].pattern_name == "B"
        assert results[-1].total_pnl < 0


class TestInsightEngineEdgeCases:
    """Edge cases: empty inputs, zero values."""

    def test_empty_positions(self):
        results = InsightEngine.analyze([], {})
        assert results == []

    def test_empty_patterns_map(self):
        positions = [make_pos(pnl=100.0, pnl_pct=0.1)]
        results = InsightEngine.analyze(positions, {})
        assert results == []

    def test_all_losses_win_rate_zero(self):
        positions = [
            make_pos(pnl=-50.0, pnl_pct=-0.05),
            make_pos(pnl=-30.0, pnl_pct=-0.03),
        ]
        patterns_map = {0: ["SCALP"], 1: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert len(results) == 1
        item = results[0]
        assert item.win_count == 0
        assert item.win_rate == 0.0
        # expectancy = 0 * 0 - 1 * avg_loss = -40.0
        assert item.expectancy == -40.0

    def test_zero_pnl_is_not_win(self):
        positions = [make_pos(pnl=0.0, pnl_pct=0.0)]
        patterns_map = {0: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert results[0].win_count == 0
        assert results[0].win_rate == 0.0

    def test_one_position_appears_in_multiple_patterns(self):
        """A position tagged with multiple patterns contributes to each."""
        positions = [make_pos(pnl=100.0, pnl_pct=0.1)]
        patterns_map = {0: ["SCALP", "SWING"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert len(results) == 2
        for r in results:
            assert r.count == 1
            assert r.total_pnl == 100.0


class TestInsightEngineCostUnknown:
    """Positions with cost_known=False must be excluded from statistics."""

    def test_cost_unknown_filtered_out(self):
        positions = [
            make_pos(pnl=100.0, pnl_pct=0.1),
            _Position(pnl=0.0, pnl_pct=0.0, cost_known=False),  # unknown cost
        ]
        patterns_map = {0: ["SWING"], 1: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        # Only position 0 (cost_known=True) should contribute
        assert len(results) == 1
        assert results[0].pattern_name == "SWING"
        assert results[0].count == 1
        assert results[0].total_pnl == 100.0

    def test_all_cost_unknown_returns_empty(self):
        positions = [
            _Position(pnl=0.0, pnl_pct=0.0, cost_known=False),
        ]
        patterns_map = {0: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert results == []

    def test_mixed_cost_known_and_unknown(self):
        positions = [
            make_pos(pnl=200.0, pnl_pct=0.2),     # cost_known=True
            _Position(pnl=0.0, pnl_pct=0.0, cost_known=False),
            make_pos(pnl=-50.0, pnl_pct=-0.05),   # cost_known=True
        ]
        patterns_map = {0: ["PYRAMID"], 1: ["PYRAMID"], 2: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        # Only positions 0 and 2 should contribute
        pyramid = next(r for r in results if r.pattern_name == "PYRAMID")
        assert pyramid.count == 1
        assert pyramid.total_pnl == 200.0

        scalp = next(r for r in results if r.pattern_name == "SCALP")
        assert scalp.count == 1
        assert scalp.total_pnl == -50.0

    def test_zero_expectancy_when_no_wins_and_no_losses(self):
        """Position with pnl=0.0 -> avg_win=0, avg_loss=0 -> expectancy=0."""
        positions = [make_pos(pnl=0.0, pnl_pct=0.0)]
        patterns_map = {0: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert results[0].expectancy == 0.0
