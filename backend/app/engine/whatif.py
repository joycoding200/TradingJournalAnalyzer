"""Profit attribution: counterfactual backtest removing selected behavior patterns."""
from dataclasses import dataclass


@dataclass
class AttributionItem:
    """Result of removing a single behavioral pattern from the portfolio."""

    removed_pattern: str
    original_return: float
    what_if_return: float
    delta: float
    contribution_pct: float  # percentage contribution to total PnL
    absolute_impact: float = 0.0  # absolute PnL impact (total_pnl - filtered_pnl)


class ProfitAttribution:
    """Simulate portfolio return after removing positions tagged with a pattern."""

    @staticmethod
    def attribution_analysis(positions, patterns_map: dict[int, list[str]]) -> list[AttributionItem]:
        """Run what-if analysis for each unique pattern.

        Excludes positions where cost_known is False (pre-existing positions
        with estimated cost basis).

        For each pattern, removes all positions tagged with it and
        recomputes the portfolio return. The contribution_pct quantifies
        how much the pattern affected the overall result (0 = no effect,
        1 = most harmful/helpful).

        Args:
            positions: List of position-like objects with .pnl, .avg_entry_price,
                       .total_quantity.
            patterns_map: {position_index: [pattern_name, ...]}.

        Returns:
            List of AttributionItem sorted by contribution_pct descending.
        """
        # Filter out positions with unknown cost basis
        valid_indices = {
            i for i, p in enumerate(positions)
            if getattr(p, "cost_known", True)
        }
        valid_positions = [p for i, p in enumerate(positions) if i in valid_indices]

        if not valid_positions:
            return []

        total_invested = sum(
            p.avg_entry_price * p.total_quantity for p in valid_positions
        )
        total_pnl = sum(p.pnl for p in valid_positions)
        original_return = (
            total_pnl / total_invested if total_invested > 0 else 0.0
        )

        all_patterns: set[str] = set()
        for i, pats in patterns_map.items():
            if i in valid_indices:
                all_patterns.update(pats)

        results: list[AttributionItem] = []
        for pattern_name in all_patterns:
            filtered = [
                p
                for i, p in enumerate(positions)
                if i in valid_indices and pattern_name not in patterns_map.get(i, [])
            ]
            if not filtered:
                continue

            filtered_invested = sum(
                p.avg_entry_price * p.total_quantity for p in filtered
            )
            filtered_pnl = sum(p.pnl for p in filtered)
            what_if_return = (
                filtered_pnl / filtered_invested
                if filtered_invested > 0
                else 0.0
            )

            absolute_impact = total_pnl - filtered_pnl
            results.append(
                AttributionItem(
                    removed_pattern=pattern_name,
                    original_return=round(original_return, 4),
                    what_if_return=round(what_if_return, 4),
                    delta=round(what_if_return - original_return, 4),
                    contribution_pct=0.0,
                    absolute_impact=round(absolute_impact, 2),
                )
            )

        # Normalize contribution percentages
        if results:
            max_delta = max(abs(r.delta) for r in results)
            for r in results:
                r.contribution_pct = (
                    round(abs(r.delta) / max_delta, 4) if max_delta > 0 else 0.0
                )

        results.sort(key=lambda x: x.contribution_pct, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Phase 4 — Level 3: Rule simulation
    # ------------------------------------------------------------------

    @staticmethod
    def analyze_rule(positions, rule_type: str, params: dict):
        """Level 3: Rule simulation. Simulate what if a trading rule was enforced.

        Args:
            positions: List of position-like objects with .pnl, .pnl_pct,
                       .avg_entry_price, .total_quantity.
            rule_type: Type of rule to simulate (e.g. "stop_loss").
            params: Rule-specific parameters.

        Returns:
            Dict with original_return, what_if_return, delta, affected_positions,
            or None if rule_type is unknown.
        """
        total_invested = sum(
            p.avg_entry_price * p.total_quantity for p in positions
        )
        total_pnl = sum(p.pnl for p in positions)
        original_return = (
            total_pnl / total_invested if total_invested > 0 else 0.0
        )

        if rule_type == "stop_loss":
            loss_cap = params.get("loss_pct", 0.05)
            simulated_pnl = 0.0
            affected = 0
            for p in positions:
                if p.pnl_pct < -loss_cap:
                    capped_pnl = -loss_cap * p.avg_entry_price * p.total_quantity
                    simulated_pnl += capped_pnl
                    affected += 1
                else:
                    simulated_pnl += p.pnl
            what_if_return = (
                simulated_pnl / total_invested if total_invested > 0 else 0.0
            )
            return {
                "rule": f"stop_loss_{loss_cap}",
                "original_return": round(original_return, 4),
                "what_if_return": round(what_if_return, 4),
                "delta": round(what_if_return - original_return, 4),
                "affected_positions": affected,
            }

        return None
