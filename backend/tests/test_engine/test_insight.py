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
        # V2.2 R-multiple: expectancy = 1.0 * 0.1 - 0 * 0 = 0.1
        assert item.expectancy == 0.1

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
        # V2.2 R-multiple: expectancy = 2/3 * avg_win_pct - 1/3 * avg_loss_pct
        # avg_win_pct = (0.1+0.2)/2 = 0.15, avg_loss_pct = abs(-0.05) = 0.05
        # expectancy = 2/3 * 0.15 - 1/3 * 0.05 = 0.10 - 0.0167 = 0.08 (rounded)
        assert item.expectancy == 0.08


class TestInsightEngineMultiple:
    """Multiple patterns across positions."""

    def test_multiple_patterns(self):
        """V2.2: Primary pattern — position 1 goes to SWING (first by default conf)."""
        positions = [
            make_pos(pnl=100.0, pnl_pct=0.1),
            make_pos(pnl=50.0, pnl_pct=0.05),
            make_pos(pnl=-30.0, pnl_pct=-0.03),
        ]
        patterns_map = {0: ["SWING"], 1: ["SWING", "TREND"], 2: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        # Position 1 resolves to primary SWING (same priority, first in list)
        assert len(results) == 2  # SWING + SCALP

        swing = next(r for r in results if r.pattern_name == "SWING")
        assert swing.count == 2  # pos 0 + pos 1
        assert swing.total_pnl == 150.0

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
        # V2.2 R-multiple: expectancy = 0 * 0 - 1 * avg_loss_pct = -0.04
        assert item.expectancy == -0.04

    def test_zero_pnl_is_not_win(self):
        positions = [make_pos(pnl=0.0, pnl_pct=0.0)]
        patterns_map = {0: ["SCALP"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert results[0].win_count == 0
        assert results[0].win_rate == 0.0

    def test_one_position_appears_in_multiple_patterns(self):
        """V2.2: Primary pattern — one position → one primary bucket only."""
        positions = [make_pos(pnl=100.0, pnl_pct=0.1)]
        patterns_map = {0: ["SCALP", "SWING"]}
        results = InsightEngine.analyze(positions, patterns_map)
        assert len(results) == 1  # only primary pattern
        assert results[0].count == 1
        assert results[0].total_pnl == 100.0


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


# ============================================================================
# Fix 7: _resolve_primary — PnL attribution to primary pattern only
# ============================================================================


class TestResolvePrimary:
    """InsightEngine._resolve_primary picks one pattern per position."""

    def test_picks_highest_confidence(self):
        patterns_map = {
            0: [("SWING", 1.0), ("CHASE", 0.5)],
        }
        result = InsightEngine._resolve_primary(patterns_map)
        assert result[0] == "SWING"

    def test_ties_broken_by_exit_module(self):
        """Exit patterns (priority 0) win ties over entry (priority 1)."""
        patterns_map = {
            0: [("SWING", 1.0), ("TIGHT_STOP", 0.8), ("CHASE", 0.8)],
        }
        result = InsightEngine._resolve_primary(patterns_map)
        # TIGHT_STOP (exit) and CHASE (entry) have same confidence 0.8
        # After sorting: SWING 1.0, then among 0.8, TIGHT_STOP (exit=0) beats CHASE (entry=1)
        assert result[0] == "SWING"

    def test_returns_empty_for_empty_map(self):
        result = InsightEngine._resolve_primary({})
        assert result == {}

    def test_all_positions_get_primary(self):
        patterns_map = {
            0: [("SCALP", 1.0)],
            1: [("SWING", 1.0), ("BULL_TREND", 0.7)],
            2: [("CHASE", 0.5)],
        }
        result = InsightEngine._resolve_primary(patterns_map)
        assert len(result) == 3
        assert result[0] == "SCALP"
        assert result[1] == "SWING"
        assert result[2] == "CHASE"

    def test_empty_position_skipped(self):
        patterns_map = {
            0: [("SWING", 1.0)],
            1: [],
        }
        result = InsightEngine._resolve_primary(patterns_map)
        assert 0 in result
        assert 1 not in result


# ============================================================================
# Fix: analyze_by_category — per-category insight
# ============================================================================


class TestAnalyzeByCategory:
    """InsightEngine.analyze_by_category() — per-category aggregation."""

    def test_basic_by_category(self):
        positions = [
            make_pos(pnl=100.0, pnl_pct=0.1),
            make_pos(pnl=50.0, pnl_pct=0.05),
            make_pos(pnl=-30.0, pnl_pct=-0.03),
        ]
        category_map = {
            0: {"entry": "BREAKOUT", "holding": "SWING"},
            1: {"entry": "TREND"},
            2: {"holding": "SCALP", "risk": "TURN"},
        }
        result = InsightEngine.analyze_by_category(positions, category_map)
        assert "entry" in result
        assert "holding" in result
        assert "risk" in result
        assert len(result["entry"]) == 2  # BREAKOUT, TREND
        assert len(result["holding"]) == 2  # SWING, SCALP
        assert len(result["risk"]) == 1  # TURN

    def test_category_aggregates_count_and_pnl(self):
        positions = [
            make_pos(pnl=100.0, pnl_pct=0.1),
            make_pos(pnl=50.0, pnl_pct=0.05),
            make_pos(pnl=-30.0, pnl_pct=-0.03),
        ]
        category_map = {
            0: {"entry": "BREAKOUT"},
            1: {"entry": "BREAKOUT"},
            2: {"entry": "BREAKOUT"},
        }
        result = InsightEngine.analyze_by_category(positions, category_map)
        assert len(result["entry"]) == 1  # only BREAKOUT
        item = result["entry"][0]
        assert item.pattern_name == "BREAKOUT"
        assert item.count == 3
        assert item.win_count == 2
        assert item.total_pnl == 120.0  # 100 + 50 - 30

    def test_empty_category_map(self):
        result = InsightEngine.analyze_by_category([make_pos()], {})
        assert result == {}

    def test_empty_positions(self):
        result = InsightEngine.analyze_by_category([], {})
        assert result == {}

    def test_cost_unknown_filtered_out(self):
        class _Pos:
            def __init__(self, pnl, pnl_pct, cost_known=True):
                self.pnl = pnl
                self.pnl_pct = pnl_pct
                self.cost_known = cost_known
        positions = [
            _Pos(100.0, 0.1, True),
            _Pos(50.0, 0.05, False),  # unknown cost
        ]
        category_map = {0: {"entry": "BREAKOUT"}, 1: {"entry": "TREND"}}
        result = InsightEngine.analyze_by_category(positions, category_map)
        assert "entry" in result
        assert len(result["entry"]) == 1  # only BREAKOUT (position 0)
        assert result["entry"][0].pattern_name == "BREAKOUT"

    def test_all_cost_unknown_returns_empty(self):
        class _Pos:
            def __init__(self, pnl, pnl_pct, cost_known=True):
                self.pnl = pnl
                self.pnl_pct = pnl_pct
                self.cost_known = cost_known
        positions = [_Pos(100.0, 0.1, False)]
        category_map = {0: {"entry": "BREAKOUT"}}
        result = InsightEngine.analyze_by_category(positions, category_map)
        assert result == {}
