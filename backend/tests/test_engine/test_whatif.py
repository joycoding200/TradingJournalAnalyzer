"""Tests for ProfitAttribution -- counterfactual backtest simulation."""
from dataclasses import dataclass, field
from datetime import date

from app.engine.whatif import ProfitAttribution, AttributionItem


# -- helpers ----------------------------------------------------------------


@dataclass
class _Position:
    """Minimal position-like object for testing what-if."""
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


def make_pos(
    pnl: float = 0.0,
    avg_entry: float = 10.0,
    qty: float = 100,
) -> _Position:
    """Create a test position."""
    avg_exit = avg_entry + pnl / qty if qty else avg_entry
    pnl_pct = (avg_exit - avg_entry) / avg_entry if avg_entry else 0.0
    return _Position(
        pnl=pnl,
        pnl_pct=pnl_pct,
        avg_entry_price=avg_entry,
        total_quantity=qty,
        avg_exit_price=avg_exit,
    )


# ============================================================================
# Tests
# ============================================================================


class TestProfitAttributionBasic:
    """Basic what-if scenarios."""

    def test_returns_one_item_per_pattern(self):
        positions = [
            make_pos(pnl=100.0),
            make_pos(pnl=-50.0),
        ]
        patterns_map = {0: ["SWING"], 1: ["SCALP"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        assert len(results) == 2
        assert {r.removed_pattern for r in results} == {"SWING", "SCALP"}

    def test_original_return_same_for_all_items(self):
        positions = [
            make_pos(pnl=100.0),
            make_pos(pnl=-50.0),
        ]
        patterns_map = {0: ["SWING"], 1: ["SCALP"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        # total_invested = 1000 + 1000 = 2000, total_pnl = 50, return = 0.025
        for r in results:
            assert r.original_return == 0.025

    def test_removing_loss_pattern_improves_return(self):
        positions = [
            make_pos(pnl=200.0),
            make_pos(pnl=100.0),
            make_pos(pnl=-500.0),
        ]
        patterns_map = {0: ["A"], 1: ["A"], 2: ["TERRIBLE"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        terrible = next(r for r in results if r.removed_pattern == "TERRIBLE")
        assert terrible.what_if_return > terrible.original_return
        assert terrible.delta > 0

    def test_removing_profit_pattern_decreases_return(self):
        positions = [
            make_pos(pnl=500.0),
            make_pos(pnl=-50.0),
        ]
        patterns_map = {0: ["STAR"], 1: ["MEH"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        star = next(r for r in results if r.removed_pattern == "STAR")
        assert star.what_if_return < star.original_return
        assert star.delta < 0


class TestProfitAttributionContribution:
    """Contribution percentage calculation and sorting."""

    def test_contribution_pct_sorted_descending(self):
        positions = [
            make_pos(pnl=500.0),
            make_pos(pnl=-200.0),
            make_pos(pnl=-50.0),
        ]
        patterns_map = {0: ["A"], 1: ["B"], 2: ["C"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        scores = [r.contribution_pct for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_contribution_pct_between_zero_and_one(self):
        positions = [
            make_pos(pnl=500.0),
            make_pos(pnl=-200.0),
            make_pos(pnl=-50.0),
        ]
        patterns_map = {0: ["A"], 1: ["B"], 2: ["C"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        for r in results:
            assert 0.0 <= r.contribution_pct <= 1.0

    def test_contribution_pct_one_for_most_harmful(self):
        """The most harmful pattern should have contribution_pct=1.0."""
        positions = [
            make_pos(pnl=500.0),
            make_pos(pnl=-500.0),
            make_pos(pnl=50.0),
        ]
        patterns_map = {0: ["GOOD"], 1: ["BAD"], 2: ["MEH"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        # The pattern with largest |delta| should have contribution_pct 1.0
        assert results[0].contribution_pct == 1.0


class TestProfitAttributionEdgeCases:
    """Edge cases: empty inputs, zero values."""

    def test_empty_positions(self):
        results = ProfitAttribution.attribution_analysis([], {})
        assert results == []

    def test_empty_patterns_map(self):
        positions = [make_pos(pnl=100.0)]
        results = ProfitAttribution.attribution_analysis(positions, {})
        assert results == []

    def test_zero_invested_does_not_crash(self):
        """Positions with avg_entry_price=0 should not cause division by zero."""
        pos = _Position(
            pnl=0.0, pnl_pct=0.0, avg_entry_price=0.0, total_quantity=0
        )
        results = ProfitAttribution.attribution_analysis([pos], {0: ["SCALP"]})
        assert results == []

    def test_all_positions_have_same_pattern(self):
        """Removing the only pattern should produce empty filtered list -> skipped."""
        positions = [
            make_pos(pnl=100.0),
            make_pos(pnl=50.0),
        ]
        patterns_map = {0: ["A"], 1: ["A"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        # When we remove "A", no positions remain -> skipped
        assert results == []


class TestProfitAttributionCostUnknown:
    """Positions with cost_known=False must be excluded from analysis."""

    def test_cost_unknown_filtered_out(self):
        """cost_unknown positions should not affect totals or what-if."""
        positions = [
            make_pos(pnl=100.0),                                     # cost_known=True
            _Position(pnl=0.0, pnl_pct=0.0, cost_known=False),       # unknown
            make_pos(pnl=-50.0),                                      # cost_known=True
        ]
        patterns_map = {0: ["GOOD"], 1: ["UNKNOWN"], 2: ["BAD"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        # UNKNOWN pattern should not appear since its position is filtered out
        pattern_names = {r.removed_pattern for r in results}
        assert "UNKNOWN" not in pattern_names
        assert len(results) == 2

    def test_all_cost_unknown_returns_empty(self):
        positions = [
            _Position(pnl=100.0, pnl_pct=0.1, cost_known=False),
        ]
        results = ProfitAttribution.attribution_analysis(positions, {0: ["SCALP"]})
        assert results == []


# ============================================================================
# Phase 4 — ProfitAttribution Level 3: analyze_rule()
# ============================================================================


class TestProfitAttributionAnalyzeRule:
    """Level 3: Rule simulation."""

    def test_stop_loss_caps_losses(self):
        """Positions with pnl_pct < -5% get capped at -5%."""
        positions = [
            make_pos(pnl=200.0, avg_entry=10.0, qty=100),   # pnl_pct = 20%
            make_pos(pnl=-100.0, avg_entry=10.0, qty=100),  # pnl_pct = -10%
            make_pos(pnl=-30.0, avg_entry=10.0, qty=100),   # pnl_pct = -3%
        ]
        # pos 1 has pnl_pct=-10% < -5%, cap at -5% = -10.0*100*-0.05 = -50.0
        # total_pnl_original = 70, total_invested = 3000, original_return = 0.02333...
        # simulated: 200 + (-50) + (-30) = 120, what_if_return = 120/3000 = 0.04
        result = ProfitAttribution.analyze_rule(positions, "stop_loss", {"loss_pct": 0.05})
        assert result is not None
        assert result["rule"] == "stop_loss_0.05"
        assert result["affected_positions"] == 1
        assert result["delta"] > 0  # should improve return
        assert result["what_if_return"] == 0.04

    def test_stop_loss_no_affected(self):
        """When no positions exceed loss_pct, delta is 0."""
        positions = [
            make_pos(pnl=200.0, avg_entry=10.0, qty=100),   # pnl_pct = 20%
            make_pos(pnl=-30.0, avg_entry=10.0, qty=100),   # pnl_pct = -3%
        ]
        result = ProfitAttribution.analyze_rule(positions, "stop_loss", {"loss_pct": 0.05})
        assert result is not None
        assert result["affected_positions"] == 0
        assert result["delta"] == 0.0

    def test_stop_loss_all_capped(self):
        """All positions exceed loss_pct."""
        positions = [
            make_pos(pnl=-200.0, avg_entry=10.0, qty=100),   # pnl_pct = -20%
            make_pos(pnl=-100.0, avg_entry=10.0, qty=100),   # pnl_pct = -10%
        ]
        # Both capped at -5%: each contributes -50 pnl
        # simulated_pnl = -100, original_pnl = -300
        result = ProfitAttribution.analyze_rule(positions, "stop_loss", {"loss_pct": 0.05})
        assert result is not None
        assert result["affected_positions"] == 2

    def test_stop_loss_zero_invested_does_not_crash(self):
        pos = _Position(pnl=-100.0, pnl_pct=-0.10, avg_entry_price=0.0, total_quantity=0)
        result = ProfitAttribution.analyze_rule([pos], "stop_loss", {"loss_pct": 0.05})
        assert result is not None
        assert result["original_return"] == 0.0
        assert result["what_if_return"] == 0.0

    def test_unknown_rule_type_returns_none(self):
        positions = [make_pos(pnl=100.0)]
        result = ProfitAttribution.analyze_rule(positions, "unknown_rule", {})
        assert result is None

    def test_attribution_item_has_contribution_pct(self):
        """Verify AttributionItem uses contribution_pct not impact_score."""
        positions = [
            make_pos(pnl=500.0),
            make_pos(pnl=-200.0),
            make_pos(pnl=-50.0),
        ]
        patterns_map = {0: ["A"], 1: ["B"], 2: ["C"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        for r in results:
            assert hasattr(r, "contribution_pct")
            assert not hasattr(r, "impact_score")

    def test_attribution_item_has_absolute_impact(self):
        """Verify AttributionItem has absolute_impact field."""
        positions = [
            make_pos(pnl=500.0),
            make_pos(pnl=-200.0),
            make_pos(pnl=50.0),
        ]
        patterns_map = {0: ["GOOD"], 1: ["BAD"], 2: ["MEH"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        for r in results:
            assert hasattr(r, "absolute_impact")

    def test_absolute_impact_is_correct(self):
        """absolute_impact = total_pnl - filtered_pnl (PnL contributed by pattern)."""
        positions = [
            make_pos(pnl=500.0),
            make_pos(pnl=-200.0),
        ]
        patterns_map = {0: ["GOOD"], 1: ["BAD"]}
        results = ProfitAttribution.attribution_analysis(positions, patterns_map)
        # total_pnl = 300, total_invested = 2000, original_return = 0.15
        # GOOD removed: filtered_pnl = -200, filtered_invested = 1000 -> what_if_return = -0.2
        #   absolute_impact = 300 - (-200) = 500
        # BAD removed: filtered_pnl = 500, filtered_invested = 1000 -> what_if_return = 0.5
        #   absolute_impact = 300 - 500 = -200
        for r in results:
            if r.removed_pattern == "GOOD":
                assert r.absolute_impact == 500.0
            if r.removed_pattern == "BAD":
                assert r.absolute_impact == -200.0
