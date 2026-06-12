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
    expectancy: float = 0.0  # per-trade expected value

    @staticmethod
    def compute(positions, pattern_name):
        """Compute expectancy for a set of positions."""
        wins = [p for p in positions if p.pnl > 0]
        losses = [p for p in positions if p.pnl <= 0]
        avg_win = sum(p.pnl for p in wins) / len(wins) if wins else 0.0
        avg_loss = (
            abs(sum(p.pnl for p in losses) / len(losses)) if losses else 0.0
        )
        win_rate = len(wins) / len(positions) if positions else 0.0
        expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
        return expectancy


class InsightEngine:
    """Group positions by pattern and compute performance metrics per pattern."""

    @staticmethod
    def _resolve_primary(patterns_map: dict[int, list[tuple[str, float]]]) -> dict[int, str]:
        """Each position gets ONE primary pattern for PnL attribution.

        Picks the pattern with highest confidence. Ties broken by:
        Exit > Entry > Risk > Holding priority.

        Args:
            patterns_map: {position_index: [(pattern_name, confidence), ...]}.

        Returns:
            {position_index: primary_pattern_name}.
        """
        PRIORITY = {"exit": 0, "entry": 1, "risk": 2, "holding": 3}
        primary = {}
        for i, pats in patterns_map.items():
            if not pats:
                continue
            # Sort by confidence desc, then module priority asc
            pats_sorted = sorted(
                pats,
                key=lambda p: (-p[1], PRIORITY.get(
                    # Derive module from common naming patterns
                    "exit" if p[0] in ("TIGHT_STOP", "TRAILING_STOP", "TIME_EXIT", "LARGE_LOSS_EXIT")
                    else "entry" if p[0] in ("CHASE", "BOTTOM", "BREAKOUT", "TREND", "COUNTER_TREND", "BREAKDOWN", "FOMO")
                    else "holding" if p[0] in ("SCALP", "SWING", "POSITION")
                    else "risk",
                    PRIORITY.get("risk", 2),
                )),
            )
            primary[i] = pats_sorted[0][0]
        return primary

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

        by_pattern: dict[str, dict] = {}
        for i in valid_indices:
            pos = positions[i]
            for pat_name in patterns_map.get(i, []):
                if pat_name not in by_pattern:
                    by_pattern[pat_name] = {
                        "positions": [],
                        "wins": 0,
                        "total_pnl": 0.0,
                    }
                by_pattern[pat_name]["positions"].append(pos)
                by_pattern[pat_name]["total_pnl"] += pos.pnl
                if pos.pnl > 0:
                    by_pattern[pat_name]["wins"] += 1

        results: list[InsightItem] = []
        for pat_name, data in by_pattern.items():
            count = len(data["positions"])
            total_pnl_all = sum(p.pnl for p in data["positions"])
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
                )
            )

        results.sort(key=lambda x: x.total_pnl, reverse=True)
        return results
