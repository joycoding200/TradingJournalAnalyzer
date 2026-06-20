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
    def analyze_rule(positions, rule_type: str, params: dict, market_data: dict = None):
        """Level 3: Rule simulation with intraday data (V2.1).

        V2.1: stop_loss now checks daily bar LOW prices during the holding
        period to determine if the stop would have been triggered intraday.
        This is true backtesting, not PnL truncation.

        Args:
            positions: List of position-like objects with .pnl, .pnl_pct,
                       .avg_entry_price, .total_quantity, .symbol,
                       .entry_date, .exit_date.
            rule_type: Type of rule to simulate (e.g. "stop_loss").
            params: Rule-specific parameters.
            market_data: {symbol: {date_str: {low}}} for intraday checks.

        Returns:
            Dict with original_return, what_if_return, delta, affected_positions,
            or None if rule_type is unknown.
        """
        from datetime import date

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
                did_trigger = False
                # The position's real PnL already has full commissions
                # subtracted. To keep the counterfactual on the same fee
                # basis, subtract the same commission from the capped/truncated
                # PnL of triggered positions. Otherwise the stop-loss strategy
                # looks artificially better than reality. See P1b.
                pos_commission = getattr(p, "total_commission", 0.0) or 0.0

                if market_data:
                    symbol_data = market_data.get(p.symbol, {})
                    entry_price = p.avg_entry_price
                    stop_price = entry_price * (1 - loss_cap)

                    for date_str in sorted(symbol_data):
                        bar_date = date.fromisoformat(date_str)
                        if p.entry_date <= bar_date <= p.exit_date:
                            bar = symbol_data[date_str]
                            bar_low = bar.get("low", entry_price)
                            if bar_low <= stop_price:
                                # Stop triggered intraday.
                                # If opened below stop (gap-down), fill at open.
                                bar_open = bar.get("open", stop_price)
                                fill_price = min(bar_open, stop_price)
                                exit_qty = p.total_quantity
                                exit_cost = fill_price * exit_qty
                                entry_cost = entry_price * exit_qty
                                simulated_pnl += exit_cost - entry_cost - pos_commission
                                affected += 1
                                did_trigger = True
                                break

                # Fallback: if no market_data or didn't trigger via intraday,
                # still check final PnL for positions without intraday data
                if not did_trigger:
                    if market_data:
                        # Had market_data but didn't trigger → keep original PnL
                        simulated_pnl += p.pnl
                    else:
                        # No market_data at all → old PnL truncation fallback
                        if p.pnl_pct < -loss_cap:
                            capped_pnl = (
                                -loss_cap * p.avg_entry_price * p.total_quantity
                                - pos_commission
                            )
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
