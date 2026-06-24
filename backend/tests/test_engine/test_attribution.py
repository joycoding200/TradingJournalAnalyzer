"""Tests for shapley_attribution — Monte Carlo Shapley value decomposition.

Verifies:
  - Single pattern → Shapley = total PnL
  - Sum of Shapley values ≈ total PnL (within sampling tolerance)
  - Empty patterns → {}
  - cost_known=False positions are excluded
"""

from dataclasses import dataclass

from app.engine.attribution import shapley_attribution

# Larger sample count for stable tests
N_SAMPLES = 10000


@dataclass
class _Pos:
    pnl: float
    cost_known: bool = True


def test_single_pattern_equals_total_pnl():
    """When only one pattern exists, its Shapley value = total PnL."""
    positions = [_Pos(100), _Pos(-50), _Pos(75)]
    patterns_map = {0: ["SCALP"], 1: ["SCALP"], 2: ["SCALP"]}
    result = shapley_attribution(positions, patterns_map, n_samples=N_SAMPLES)
    assert len(result) == 1
    assert abs(result["SCALP"] - 125.0) < 0.02


def test_shapley_sum_equals_total_pnl():
    """Sum of all Shapley values should converge to total PnL."""
    positions = [
        _Pos(100),
        _Pos(-50),
        _Pos(75),
        _Pos(200),
        _Pos(-100),
    ]
    patterns_map = {
        0: ["CHASE", "SWING"],
        1: ["BOTTOM", "SCALP"],
        2: ["CHASE", "SCALP"],
        3: ["BREAKOUT", "SWING"],
        4: ["AVERAGE_DOWN"],
    }
    result = shapley_attribution(positions, patterns_map, n_samples=N_SAMPLES)
    total_pnl = sum(p.pnl for p in positions)
    assert len(result) > 0
    # Sum of Shapley values should be within 1% of total PnL
    shapley_sum = sum(result.values())
    assert abs(shapley_sum - total_pnl) < max(abs(total_pnl) * 0.01, 0.1)


def test_empty_patterns_returns_empty_dict():
    """No patterns → empty result."""
    positions = [_Pos(100), _Pos(-50)]
    result = shapley_attribution(positions, {}, n_samples=100)
    assert result == {}


def test_no_valid_positions_returns_empty():
    """All positions filtered by cost_known=False → empty result."""
    positions = [_Pos(100, cost_known=False), _Pos(-50, cost_known=False)]
    # positions exist but cost_known=False for all
    result = shapley_attribution(positions, {0: ["SCALP"]}, n_samples=100)
    assert result == {}


def test_cost_known_false_excluded():
    """Positions with cost_known=False are excluded from Shapley calculation."""
    positions = [
        _Pos(100, cost_known=True),
        _Pos(-50, cost_known=False),  # excluded
        _Pos(75, cost_known=True),
    ]
    patterns_map = {0: ["CHASE"], 1: ["CHASE"], 2: ["SWING"]}
    result = shapley_attribution(positions, patterns_map, n_samples=N_SAMPLES)
    shapley_sum = sum(result.values())
    # Only valid positions: 100 + 75 = 175
    assert abs(shapley_sum - 175.0) < 1.0


def test_non_overlapping_patterns():
    """Patterns that don't share positions → each gets its own positions' PnL."""
    positions = [_Pos(100), _Pos(-50), _Pos(75)]
    patterns_map = {
        0: ["CHASE"],
        1: ["BOTTOM"],
        2: ["SWING"],
    }
    result = shapley_attribution(positions, patterns_map, n_samples=N_SAMPLES)
    assert len(result) == 3
    assert abs(result["CHASE"] - 100.0) < 0.1
    assert abs(result["BOTTOM"] - (-50.0)) < 0.1
    assert abs(result["SWING"] - 75.0) < 0.1
