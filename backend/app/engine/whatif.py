"""What-If engine (whatif.py).

Two main capabilities:
  1. ProfitAttribution — counterfactual backtest: remove positions matching a
     behavior pattern and recompute total PnL to measure that pattern's impact.
     This is a *rule-based* "what if this pattern didn't exist" analysis.
  2. Stop-loss simulation — replay positions with a trailing-stop rule to
     estimate how much loss could have been avoided.

NOTE: For *statistical* pattern contribution (Shapley values / Monte Carlo
decomposition), see attribution.py. The two modules address different questions:
  - attribution.py: "How much did each pattern contribute?" (game-theoretic)
  - whatif.py:     "What if this pattern didn't exist?"   (counterfactual)
"""
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
                        # T+1: A股当日买入不可卖出，从 entry_date 次日起判断触发
                        if p.entry_date < bar_date <= p.exit_date:
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

        if rule_type == "stop_loss_large_loss":
            # Counterfactual: apply a stop-loss ONLY to positions that ended
            # as large losses (pnl_pct < -8%, same threshold as LARGE_LOSS_EXIT).
            # Answers "if I had set a 5% stop on just the big losers, what
            # would my return be?" — the question the outcome-tag attribution
            # (which removes LARGE_LOSS_EXIT wholesale) cannot answer.
            loss_cap = params.get("loss_pct", 0.05)
            large_loss_threshold = params.get("large_loss_pct", -0.08)
            simulated_pnl = 0.0
            affected = 0

            for p in positions:
                pos_commission = getattr(p, "total_commission", 0.0) or 0.0

                # Only replay positions that ended as a large loss; others
                # keep their original PnL.
                if p.pnl_pct >= large_loss_threshold:
                    simulated_pnl += p.pnl
                    continue

                did_trigger = False
                if market_data:
                    symbol_data = market_data.get(p.symbol, {})
                    entry_price = p.avg_entry_price
                    stop_price = entry_price * (1 - loss_cap)

                    for date_str in sorted(symbol_data):
                        bar_date = date.fromisoformat(date_str)
                        # T+1: A股当日买入不可卖出，从 entry_date 次日起判断触发
                        if p.entry_date < bar_date <= p.exit_date:
                            bar = symbol_data[date_str]
                            bar_low = bar.get("low", entry_price)
                            if bar_low <= stop_price:
                                bar_open = bar.get("open", stop_price)
                                fill_price = min(bar_open, stop_price)
                                exit_qty = p.total_quantity
                                exit_cost = fill_price * exit_qty
                                entry_cost = entry_price * exit_qty
                                simulated_pnl += exit_cost - entry_cost - pos_commission
                                affected += 1
                                did_trigger = True
                                break

                if not did_trigger:
                    # Large-loss position but no intraday trigger (or no
                    # market_data): fall back to PnL truncation at the cap.
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
                "rule": f"stop_loss_large_loss_{loss_cap}",
                "original_return": round(original_return, 4),
                "what_if_return": round(what_if_return, 4),
                "delta": round(what_if_return - original_return, 4),
                "affected_positions": affected,
            }

        if rule_type == "trailing_stop":
            # 移动止损：跟踪持仓期间最高价(high)，从最高点回撤 trail_pct 触发卖出。
            # 止损价随最高价动态上移(只上不下)，盈利仓位触发后锁定部分利润。
            # T+1：从 entry_date 次日起判断触发。
            trail_pct = params.get("trail_pct", 0.08)
            simulated_pnl = 0.0
            affected = 0

            for p in positions:
                pos_commission = getattr(p, "total_commission", 0.0) or 0.0
                did_trigger = False

                if market_data:
                    symbol_data = market_data.get(p.symbol, {})
                    entry_price = p.avg_entry_price
                    max_high = entry_price
                    stop_price = entry_price * (1 - trail_pct)

                    for date_str in sorted(symbol_data):
                        bar_date = date.fromisoformat(date_str)
                        if p.entry_date < bar_date <= p.exit_date:
                            bar = symbol_data[date_str]
                            bar_high = bar.get("high", entry_price)
                            bar_low = bar.get("low", entry_price)
                            # 跟踪最高价，止损价只上不下
                            if bar_high > max_high:
                                max_high = bar_high
                                new_stop = max_high * (1 - trail_pct)
                                if new_stop > stop_price:
                                    stop_price = new_stop
                            # 盘中触及止损价触发
                            if bar_low <= stop_price:
                                bar_open = bar.get("open", stop_price)
                                fill_price = min(bar_open, stop_price)
                                exit_qty = p.total_quantity
                                exit_cost = fill_price * exit_qty
                                entry_cost = entry_price * exit_qty
                                simulated_pnl += exit_cost - entry_cost - pos_commission
                                affected += 1
                                did_trigger = True
                                break

                if not did_trigger:
                    if market_data:
                        simulated_pnl += p.pnl
                    else:
                        # 无行情 fallback：退化为固定止损（按 -trail_pct 截断）
                        if p.pnl_pct < -trail_pct:
                            capped_pnl = (
                                -trail_pct * p.avg_entry_price * p.total_quantity
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
                "rule": f"trailing_stop_{trail_pct}",
                "original_return": round(original_return, 4),
                "what_if_return": round(what_if_return, 4),
                "delta": round(what_if_return - original_return, 4),
                "affected_positions": affected,
            }

        if rule_type == "take_profit":
            # 固定止盈：价格涨到 entry_price × (1 + profit_pct) 触发卖出。
            # 截断利润方向的反事实——回答"机械止盈会多赚还是少赚"。
            # T+1：从 entry_date 次日起判断触发。
            profit_pct = params.get("profit_pct", 0.10)
            simulated_pnl = 0.0
            affected = 0

            for p in positions:
                pos_commission = getattr(p, "total_commission", 0.0) or 0.0
                did_trigger = False

                if market_data:
                    symbol_data = market_data.get(p.symbol, {})
                    entry_price = p.avg_entry_price
                    target_price = entry_price * (1 + profit_pct)

                    for date_str in sorted(symbol_data):
                        bar_date = date.fromisoformat(date_str)
                        if p.entry_date < bar_date <= p.exit_date:
                            bar = symbol_data[date_str]
                            bar_high = bar.get("high", entry_price)
                            if bar_high >= target_price:
                                # 跳空高开按开盘成交，否则按目标价
                                bar_open = bar.get("open", target_price)
                                fill_price = max(bar_open, target_price)
                                exit_qty = p.total_quantity
                                exit_cost = fill_price * exit_qty
                                entry_cost = entry_price * exit_qty
                                simulated_pnl += exit_cost - entry_cost - pos_commission
                                affected += 1
                                did_trigger = True
                                break

                if not did_trigger:
                    if market_data:
                        simulated_pnl += p.pnl
                    else:
                        # 无行情 fallback：pnl_pct > profit_pct 则按 +profit_pct 截断
                        if p.pnl_pct > profit_pct:
                            capped_pnl = (
                                profit_pct * p.avg_entry_price * p.total_quantity
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
                "rule": f"take_profit_{profit_pct}",
                "original_return": round(original_return, 4),
                "what_if_return": round(what_if_return, 4),
                "delta": round(what_if_return - original_return, 4),
                "affected_positions": affected,
            }

        if rule_type == "trailing_take_profit":
            # 移动止盈(模式A：持仓期间保护)：盈利达 activation_pct 才激活移动止损保护，
            # 未激活前不干预；激活后 stop_price = max(max_high×(1-trail_pct), entry_price) 确保不亏出。
            # 回答"让利润奔跑+保护利润"的反事实。T+1：从 entry_date 次日起判断触发。
            activation_pct = params.get("activation_pct", 0.05)
            trail_pct = params.get("trail_pct", 0.05)
            simulated_pnl = 0.0
            affected = 0

            for p in positions:
                pos_commission = getattr(p, "total_commission", 0.0) or 0.0
                did_trigger = False

                if market_data:
                    symbol_data = market_data.get(p.symbol, {})
                    entry_price = p.avg_entry_price
                    activation_price = entry_price * (1 + activation_pct)
                    max_high = entry_price
                    activated = False
                    stop_price = None

                    for date_str in sorted(symbol_data):
                        bar_date = date.fromisoformat(date_str)
                        if p.entry_date < bar_date <= p.exit_date:
                            bar = symbol_data[date_str]
                            bar_high = bar.get("high", entry_price)
                            bar_low = bar.get("low", entry_price)

                            if bar_high > max_high:
                                max_high = bar_high

                            # 盈利达激活阈值，启动移动止损保护
                            if not activated and bar_high >= activation_price:
                                activated = True
                                # 确保不亏出：止损价不低于入场价
                                stop_price = max(max_high * (1 - trail_pct), entry_price)

                            if activated:
                                new_stop = max_high * (1 - trail_pct)
                                if new_stop > stop_price:
                                    stop_price = new_stop
                                # 盘中触及止损价触发
                                if bar_low <= stop_price:
                                    bar_open = bar.get("open", stop_price)
                                    fill_price = min(bar_open, stop_price)
                                    exit_qty = p.total_quantity
                                    exit_cost = fill_price * exit_qty
                                    entry_cost = entry_price * exit_qty
                                    simulated_pnl += exit_cost - entry_cost - pos_commission
                                    affected += 1
                                    did_trigger = True
                                    break

                if not did_trigger:
                    if market_data:
                        # 未激活或激活后未触发 → 保持原 PnL
                        simulated_pnl += p.pnl
                    else:
                        # 无行情 fallback：pnl_pct > activation_pct 则按 +activation_pct 截断
                        if p.pnl_pct > activation_pct:
                            capped_pnl = (
                                activation_pct * p.avg_entry_price * p.total_quantity
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
                "rule": f"trailing_take_profit_{activation_pct}_{trail_pct}",
                "original_return": round(original_return, 4),
                "what_if_return": round(what_if_return, 4),
                "delta": round(what_if_return - original_return, 4),
                "affected_positions": affected,
            }

        return None
