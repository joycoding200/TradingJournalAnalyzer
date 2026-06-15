"""Insight engine: aggregate positions by behavior pattern and compute statistics."""
from dataclasses import dataclass


@dataclass
class InsightItem:
    """Aggregated statistics for a single behavioral pattern."""

    pattern_name: str
    count: int
    win_count: int
    win_rate: float
    total_pnl: float
    avg_pnl_pct: float
    expectancy: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0  # per-trade expected value

    @staticmethod
    def compute(positions, pattern_name):
        """Compute expectancy as R-multiple (based on pnl_pct, not absolute PnL).

        Uses percentage returns to avoid position-size bias.
        """
        wins = [p for p in positions if p.pnl > 0]
        losses = [p for p in positions if p.pnl <= 0]
        avg_win_pct = sum(p.pnl_pct for p in wins) / len(wins) if wins else 0.0
        avg_loss_pct = (
            abs(sum(p.pnl_pct for p in losses) / len(losses)) if losses else 0.0
        )
        win_rate = len(wins) / len(positions) if positions else 0.0
        expectancy = win_rate * avg_win_pct - (1 - win_rate) * avg_loss_pct
        return expectancy


class InsightEngine:
    """Group positions by pattern and compute performance metrics per pattern."""

    # Priority for primary pattern selection (lower = higher priority)
    # outcome > behavior > market_env > psychology
    _DIM_PRIORITY: dict[str, int] = {
        "outcome": 0, "behavior": 1, "market_env": 2, "psychology": 3,
    }

    @staticmethod
    def _resolve_primary(
        patterns_map: dict[int, list[str | tuple[str, float]]],
    ) -> dict[int, str]:
        """Each position gets ONE primary pattern for PnL attribution.

        Picks the pattern with highest confidence. Ties broken by dimension priority:
        outcome > behavior > market_env > psychology.

        Accepts both flat name lists and (name, confidence) tuples.
        """
        primary = {}
        for i, pats in patterns_map.items():
            if not pats:
                continue
            # Normalize to (name, confidence, dimension)
            normalized = []
            for p in pats:
                if isinstance(p, str):
                    name = p
                    conf = 0.5
                else:
                    name, conf = p[0], p[1]
                dim = InsightEngine._dim_for_pattern(name)
                normalized.append((name, conf, dim))
            pats_sorted = sorted(
                normalized,
                key=lambda p: (-p[1], InsightEngine._DIM_PRIORITY.get(p[2], 99)),
            )
            primary[i] = pats_sorted[0][0]
        return primary

    @staticmethod
    def _dim_for_pattern(name: str) -> str:
        """Map pattern name to its dimension for priority resolution."""
        if name in ("TIGHT_STOP", "TRAILING_STOP", "TIME_EXIT", "LARGE_LOSS_EXIT"):
            return "outcome"
        if name in ("CHASE", "BOTTOM", "BREAKOUT", "PYRAMID", "AVERAGE_DOWN",
                    "TURN", "SCALP", "SWING", "POSITION", "FOMO"):
            return "behavior"
        if name in ("BULL_TREND", "BEAR_TREND", "BREAKDOWN"):
            return "market_env"
        if name in ("POSSIBLE_REVENGE", "OVERTRADING", "HOLD_LOSER", "CUT_WINNER", "PSY_FOMO"):
            return "psychology"
        return "behavior"

    @staticmethod
    def analyze(positions, patterns_map: dict[int, list[str]]) -> list[InsightItem]:
        """Analyze positions grouped by behavioral pattern.

        Excludes positions where cost_known is False (pre-existing positions
        with estimated cost basis).

        Args:
            positions: List of position-like objects with .pnl and .pnl_pct.
            patterns_map: {position_index: [pattern_name, ...]}.

        Returns:
            List of InsightItem sorted by expectancy descending.
        """
        # Filter out positions with unknown cost basis
        valid_indices = [
            i for i, p in enumerate(positions)
            if getattr(p, "cost_known", True)
        ]

        # V2.2: use primary pattern — one position → one pattern bucket
        primary_map = InsightEngine._resolve_primary(patterns_map)

        by_pattern: dict[str, dict] = {}
        for i in valid_indices:
            primary = primary_map.get(i)
            if not primary:
                continue
            pos = positions[i]
            if primary not in by_pattern:
                by_pattern[primary] = {
                    "positions": [],
                    "wins": 0,
                    "total_pnl": 0.0,
                }
            by_pattern[primary]["positions"].append(pos)
            by_pattern[primary]["total_pnl"] += pos.pnl
            if pos.pnl > 0:
                by_pattern[primary]["wins"] += 1

        results: list[InsightItem] = []
        for pat_name, data in by_pattern.items():
            count = len(data["positions"])
            total_pnl_all = sum(p.pnl for p in data["positions"])
            gross_profit = sum(p.pnl for p in data["positions"] if p.pnl > 0)
            gross_loss = abs(sum(p.pnl for p in data["positions"] if p.pnl < 0))
            expectancy = InsightItem.compute(data["positions"], pat_name)
            results.append(
                InsightItem(
                    pattern_name=pat_name,
                    count=count,
                    win_count=data["wins"],
                    win_rate=data["wins"] / count if count > 0 else 0.0,
                    total_pnl=round(total_pnl_all, 2),
                    avg_pnl_pct=(
                        round(sum(p.pnl_pct for p in data["positions"]) / count, 4)
                        if count > 0
                        else 0.0
                    ),
                    expectancy=round(expectancy, 2),
                    gross_profit=round(gross_profit, 2),
                    gross_loss=round(gross_loss, 2),
                )
            )

        results.sort(key=lambda x: x.total_pnl, reverse=True)
        return results

    @staticmethod
    def analyze_by_category(positions, category_map: dict[int, dict[str, str]]) -> dict[str, list[InsightItem]]:
        """Analyze positions grouped by (category, pattern) pairs.

        Args:
            positions: List of position-like objects with .pnl and .pnl_pct.
            category_map: {position_index: {category: pattern_name}}.

        Returns:
            {category_name: [InsightItem sorted by sample-weight score]}.
        """
        import math

        valid_indices = [
            i for i, p in enumerate(positions)
            if getattr(p, "cost_known", True)
        ]

        by_category: dict[str, dict[str, dict]] = {}
        for i in valid_indices:
            pos = positions[i]
            cats = category_map.get(i, {})
            for cat, pat_name in cats.items():
                if cat not in by_category:
                    by_category[cat] = {}
                if pat_name not in by_category[cat]:
                    by_category[cat][pat_name] = {"positions": [], "wins": 0}
                by_category[cat][pat_name]["positions"].append(pos)
                if pos.pnl > 0:
                    by_category[cat][pat_name]["wins"] += 1

        result = {}
        for cat, pat_data in by_category.items():
            items = []
            for pat_name, data in pat_data.items():
                positions_in_cat = data["positions"]
                count = len(positions_in_cat)
                if count == 0:
                    continue
                total_pnl = sum(p.pnl for p in positions_in_cat)
                wins = data["wins"]
                win_rate = wins / count
                expectancy = InsightItem.compute(positions_in_cat, pat_name)
                # Sample-size-weighted score
                weight = math.log(max(count, 5)) / math.log(5)
                weighted_score = total_pnl * weight
                gross_profit = sum(p.pnl for p in positions_in_cat if p.pnl > 0)
                gross_loss = abs(sum(p.pnl for p in positions_in_cat if p.pnl < 0))
                items.append(InsightItem(
                    pattern_name=pat_name, count=count, win_count=wins,
                    win_rate=round(win_rate, 4), total_pnl=round(total_pnl, 2),
                    avg_pnl_pct=round(sum(p.pnl_pct for p in positions_in_cat) / count, 4),
                    expectancy=round(expectancy, 2),
                    gross_profit=round(gross_profit, 2),
                    gross_loss=round(gross_loss, 2),
                ))
            items.sort(key=lambda x: x.total_pnl * (math.log(max(x.count, 5)) / math.log(5)), reverse=True)
            result[cat] = items
        return result
