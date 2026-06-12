"""Pattern engine for tagging positions with behavioral labels.

Produces 20 behavior tags across three modules:
  Module 1 - Entry behavior (market-data dependent)
  Module 2 - Holding period
  Module 3 - Risk & position management (incl. Phase 3 psychological tags)
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Any


@dataclass
class PatternResult:
    """A single behavioral pattern tag attached to a position."""

    pattern_name: str
    confidence: float
    context: dict[str, Any] = field(default_factory=dict)


class PatternEngine:
    """Assign behavioral pattern tags to positions."""

    # ------------------------------------------------------------------
    # Module 2 & 3 -- available without market data
    # ------------------------------------------------------------------

    @staticmethod
    def tag_position(
        pos, all_positions: list, **kwargs
    ) -> list[PatternResult]:
        """Tag a position with holding-period and risk-management patterns.

        Args:
            pos: A position-like object with holding_days, pnl_pct,
                symbol, entry_date, exit_date, avg_entry_price.
            all_positions: All positions in the analysis period.
            **kwargs: Supports 'trades' (raw trade list) and
                'all_trades' (all raw trades for trade-level analysis).

        Returns:
            List of PatternResult instances.
        """
        tags: list[PatternResult] = []

        # ----- Module 2: Holding period ---------------------------------
        if pos.holding_days < 3:
            tags.append(
                PatternResult(
                    "SCALP",
                    1.0,
                    {"holding_days": pos.holding_days},
                )
            )
        elif pos.holding_days <= 30:
            tags.append(
                PatternResult(
                    "SWING",
                    1.0,
                    {"holding_days": pos.holding_days},
                )
            )
        else:
            tags.append(
                PatternResult(
                    "POSITION",
                    1.0,
                    {"holding_days": pos.holding_days},
                )
            )

        # ----- Module 3: Risk & position management ---------------------
        # Trades for analysis (passed via kwargs)
        all_trades = kwargs.get("all_trades")

        # PYRAMID / AVERAGE_DOWN
        same_symbol_positions = [
            p for p in all_positions if p.symbol == pos.symbol
        ]
        same_symbol_positions.sort(key=lambda p: p.entry_date)

        if len(same_symbol_positions) > 1:
            first = same_symbol_positions[0]

            if all_trades is not None:
                # P0-3/P0-4: Trade-level price comparison
                same_symbol_trades = [
                    t for t in all_trades
                    if t.symbol == pos.symbol and t.side == "BUY"
                ]
                same_symbol_trades.sort(key=lambda t: t.datetime)
                if len(same_symbol_trades) >= 2:
                    first_buy_price = same_symbol_trades[0].price
                    last_buy_price = same_symbol_trades[-1].price
                    last_buy_date = same_symbol_trades[-1].datetime.date()

                    # PYRAMID: higher price while still holding
                    if last_buy_price > first_buy_price * 1.02:
                        # Check if there was an open position when this buy happened
                        for prev_pos in all_positions:
                            if (prev_pos.symbol == pos.symbol
                                    and prev_pos.entry_date <= last_buy_date <= prev_pos.exit_date):
                                tags.append(
                                    PatternResult(
                                        "PYRAMID",
                                        0.8,
                                        {
                                            "last_buy_price": last_buy_price,
                                            "first_buy_price": first_buy_price,
                                            "buy_date": str(last_buy_date),
                                        },
                                    )
                                )
                                break

                    # AVERAGE_DOWN: second buy at significantly lower price
                    if last_buy_price < first_buy_price * 0.95:
                        tags.append(
                            PatternResult(
                                "AVERAGE_DOWN",
                                0.8,
                                {
                                    "last_buy_price": last_buy_price,
                                    "first_buy_price": first_buy_price,
                                },
                            )
                        )
            else:
                # Fallback: Position-level comparison (backward compatible)
                # PYRAMID: adding at a HIGHER price with time separation >= 1 day
                if pos.avg_entry_price > first.avg_entry_price * 1.02:
                    days_gap = (pos.entry_date - first.entry_date).days
                    if days_gap >= 1:
                        tags.append(
                            PatternResult(
                                "PYRAMID",
                                0.8,
                                {
                                    "avg_entry": pos.avg_entry_price,
                                    "first_entry_avg": first.avg_entry_price,
                                    "days_gap": days_gap,
                                },
                            )
                        )
                # AVERAGE_DOWN: adding at a significantly LOWER price (>= 5%)
                if pos.avg_entry_price < first.avg_entry_price * 0.95:
                    tags.append(
                        PatternResult(
                            "AVERAGE_DOWN",
                            0.8,
                            {
                                "avg_entry": pos.avg_entry_price,
                                "first_entry_avg": first.avg_entry_price,
                            },
                        )
                    )

        # TURN -- intraday round trip (做T)
        trades = kwargs.get("trades")
        if trades is not None:
            # Check raw trades for same-symbol same-date opposite-side pairs
            same_symbol_trades = [t for t in trades if t.symbol == pos.symbol]
            dates_with_both: set = set()
            buy_dates: set = set()
            sell_dates: set = set()
            for t in same_symbol_trades:
                if t.side.upper() == "BUY":
                    buy_dates.add(t.datetime.date())  # P0-2: fix t.date -> t.datetime.date()
                elif t.side.upper() == "SELL":
                    sell_dates.add(t.datetime.date())  # P0-2: fix t.date -> t.datetime.date()
            dates_with_both = buy_dates & sell_dates
            if dates_with_both:
                tags.append(
                    PatternResult(
                        "TURN",
                        0.7,
                        {
                            "turn_dates": sorted(str(d) for d in dates_with_both),
                        },
                    )
                )
        elif pos.entry_date == pos.exit_date and len(same_symbol_positions) > 1:
            tags.append(
                PatternResult(
                    "TURN",
                    0.7,
                    {"entry_date": str(pos.entry_date)},
                )
            )

        # SMALL_LOSS_EXIT / TAKE_PROFIT
        if -0.08 <= pos.pnl_pct < 0 and pos.holding_days <= 10:
            tags.append(
                PatternResult(
                    "SMALL_LOSS_EXIT",
                    0.6,
                    {"pnl_pct": pos.pnl_pct, "holding_days": pos.holding_days},
                )
            )
        if pos.pnl_pct > 0:
            if pos.pnl_pct < 0.05 and pos.holding_days < 5:
                tags.append(
                    PatternResult(
                        "QUICK_PROFIT",
                        0.6,
                        {"pnl_pct": pos.pnl_pct, "holding_days": pos.holding_days},
                    )
                )
            if 0.05 <= pos.pnl_pct <= 0.20:
                tags.append(
                    PatternResult(
                        "NORMAL_PROFIT",
                        0.6,
                        {"pnl_pct": pos.pnl_pct},
                    )
                )
            if pos.pnl_pct > 0.20:
                tags.append(
                    PatternResult(
                        "BIG_WIN",
                        0.6,
                        {"pnl_pct": pos.pnl_pct},
                    )
                )

        # ----- Priority resolution for overlapping tags -------------------
        tag_names = {t.pattern_name for t in tags}

        return tags

    # ------------------------------------------------------------------
    # Cooldown detection (separate from tag_position -- CASH is not a trade behavior)
    # ------------------------------------------------------------------

    @staticmethod
    def detect_cooldowns(
        pos, all_positions: list
    ) -> list[PatternResult]:
        """Detect cooldown periods between positions.

        A 'CASH' tag is emitted when the gap since the last position
        exceeds 30 calendar days, or when this is the first position
        in the analysis period.

        Args:
            pos: A position-like object with entry_date.
            all_positions: All positions in the analysis period.

        Returns:
            List of PatternResult instances (may include CASH).
        """
        results: list[PatternResult] = []
        earlier = [p for p in all_positions if p.exit_date < pos.entry_date]
        if not earlier:
            results.append(
                PatternResult(
                    "CASH", 0.5, {"reason": "first position in period"}
                )
            )
        else:
            last_exit = max(p.exit_date for p in earlier)
            gap = (pos.entry_date - last_exit).days
            if gap > 30:
                results.append(
                    PatternResult(
                        "CASH",
                        0.5,
                        {
                            "gap_days": gap,
                            "last_exit": str(last_exit),
                        },
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Module 1 -- requires market-data dictionary
    # ------------------------------------------------------------------

    @staticmethod
    def tag_market_patterns(
        pos, market_data: dict[str, dict[str, dict[str, float]]]
    ) -> list[PatternResult]:
        """Tag entry/exit behavior using price & moving-average data.

        Expected market_data structure per date:
          {open, high, low, close, ma5, ma10, ma20, ma60}
        Optionally also:
          {volume, avg_volume_20d}

        Args:
            pos: A position-like object with symbol, entry_date, exit_date.
            market_data: Nested dict keyed by symbol -> date_str ->
                per-date dict (see above).

        Returns:
            List of PatternResult instances.
        """
        tags: list[PatternResult] = []

        symbol_data = market_data.get(pos.symbol)
        if not symbol_data:
            return tags

        entry_str = pos.entry_date.isoformat()
        exit_str = pos.exit_date.isoformat()
        entry_data = symbol_data.get(entry_str)
        exit_data = symbol_data.get(exit_str)

        if not entry_data:
            return tags

        dates = sorted(symbol_data.keys())
        entry_idx = dates.index(entry_str)
        entry_close = entry_data["close"]

        # -- CHASE: entry close vs 5 days ago > +15% --------------------
        #   Full confidence (0.7) when MA deviation AND high proximity
        #   both hold. Otherwise lower confidence (0.5).
        if entry_idx >= 5:
            d5 = dates[entry_idx - 5]
            close_5 = symbol_data[d5]["close"]
            chg = (entry_close - close_5) / close_5
            if chg > 0.15:
                has_ma_deviation = entry_close > entry_data.get("ma20", float("inf")) * 1.10
                has_high_proximity = False
                if entry_idx >= 20:
                    prev_highs = [
                        symbol_data[dates[i]]["high"]
                        for i in range(entry_idx - 20, entry_idx)
                    ]
                    max_high = max(prev_highs)
                    has_high_proximity = entry_close >= max_high * 0.97
                confidence = 0.7 if (has_ma_deviation and has_high_proximity) else 0.5
                tags.append(
                    PatternResult(
                        "CHASE",
                        confidence,
                        {
                            "change_pct": round(chg, 4),
                            "from_date": d5,
                        },
                    )
                )

        # -- FOMO: entry near day's high after streak of up days -------
        if entry_idx >= 5:
            up_count = 0
            for i in range(entry_idx - 5, entry_idx):
                prev = symbol_data[dates[i - 1]]["close"]
                curr = symbol_data[dates[i]]["close"]
                if curr > prev:
                    up_count += 1
            if up_count >= 3 and entry_close >= entry_data["high"] * 0.98:
                tags.append(
                    PatternResult(
                        "FOMO",
                        0.7,
                        {
                            "up_days_5": up_count,
                            "entry_close": entry_close,
                            "day_high": entry_data["high"],
                        },
                    )
                )

        # -- BOTTOM: entry close vs 5 days ago < -15% -------------------
        #   Must also be in downtrend (ma20 < ma60).
        if entry_idx >= 5:
            d5 = dates[entry_idx - 5]
            close_5 = symbol_data[d5]["close"]
            chg = (entry_close - close_5) / close_5
            if chg < -0.15:
                ma20 = entry_data.get("ma20")
                ma60 = entry_data.get("ma60")
                if ma20 is not None and ma60 is not None and ma20 < ma60:
                    tags.append(
                        PatternResult(
                            "BOTTOM",
                            0.7,
                            {
                                "change_pct": round(chg, 4),
                                "from_date": d5,
                            },
                        )
                    )

        # -- BREAKOUT: entry close > max(prev 20d high) ----------------
        #   Volume confirmation when volume data is available.
        if entry_idx >= 20:
            prev_highs = [
                symbol_data[dates[i]]["high"]
                for i in range(entry_idx - 20, entry_idx)
            ]
            max_high = max(prev_highs)
            if entry_close > max_high:
                entry_volume = entry_data.get("volume")
                avg_volume_20d = entry_data.get("avg_volume_20d")
                has_volume_data = (
                    entry_volume is not None and avg_volume_20d is not None
                )

                if has_volume_data:
                    if entry_volume > avg_volume_20d * 1.5:
                        tags.append(
                            PatternResult(
                                "BREAKOUT",
                                0.7,
                                {
                                    "entry_close": entry_close,
                                    "max_prev_20_high": max_high,
                                    "volume": entry_volume,
                                    "avg_volume_20d": avg_volume_20d,
                                },
                            )
                        )
                else:
                    # Backward compat: no volume data, tag at lower confidence
                    tags.append(
                        PatternResult(
                            "BREAKOUT",
                            0.5,
                            {
                                "entry_close": entry_close,
                                "max_prev_20_high": max_high,
                            },
                        )
                    )

        # -- TREND / COUNTER_TREND: MA relationship + price confirmation -
        _maybe_ma_tag(
            tags,
            entry_data,
            "TREND",
            lambda ma20, ma60: ma20 > ma60 and entry_close > ma20,
        )
        _maybe_ma_tag(
            tags,
            entry_data,
            "COUNTER_TREND",
            lambda ma20, ma60: ma20 < ma60 and entry_close < ma20,
        )

        # -- BREAKDOWN: exit close < min(prev 20d low) -----------------
        if exit_data and exit_str in dates:
            exit_idx = dates.index(exit_str)
            if exit_idx >= 20:
                prev_lows = [
                    symbol_data[dates[i]]["low"]
                    for i in range(exit_idx - 20, exit_idx)
                ]
                min_low = min(prev_lows)
                if exit_data["close"] < min_low:
                    tags.append(
                        PatternResult(
                            "BREAKDOWN",
                            0.7,
                            {
                                "exit_close": exit_data["close"],
                                "min_prev_20_low": min_low,
                            },
                        )
                    )

        return tags

    # ------------------------------------------------------------------
    # Phase 4 — Tag hierarchy resolution (L1 -> L2 sub_pattern)
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_hierarchy(tags: list[PatternResult]) -> list[PatternResult]:
        """Post-process tags to establish L1->L2 hierarchy via context.sub_pattern.

        L1 trend/counter-trend tags get a sub_pattern:
          TREND + BREAKOUT -> TREND.sub_pattern = BREAKOUT
          TREND + CHASE    -> TREND.sub_pattern = CHASE
          COUNTER_TREND + BOTTOM -> COUNTER_TREND.sub_pattern = BOTTOM
          COUNTER_TREND + BREAKDOWN -> COUNTER_TREND.sub_pattern = BREAKDOWN
        """
        trend_tags = {t.pattern_name for t in tags}

        if "TREND" in trend_tags and "BREAKOUT" in trend_tags:
            for t in tags:
                if t.pattern_name == "TREND":
                    t.context["sub_pattern"] = "BREAKOUT"
        elif "TREND" in trend_tags and "CHASE" in trend_tags:
            for t in tags:
                if t.pattern_name == "TREND":
                    t.context["sub_pattern"] = "CHASE"
        if "COUNTER_TREND" in trend_tags and "BOTTOM" in trend_tags:
            for t in tags:
                if t.pattern_name == "COUNTER_TREND":
                    t.context["sub_pattern"] = "BOTTOM"
        elif "COUNTER_TREND" in trend_tags and "BREAKDOWN" in trend_tags:
            for t in tags:
                if t.pattern_name == "COUNTER_TREND":
                    t.context["sub_pattern"] = "BREAKDOWN"

        return tags

    # ------------------------------------------------------------------
    # P1-6: Psychological pattern suggestions (AI推测 layer)
    # These are suggestions, not hard behavioral tags. They indicate
    # potential psychological patterns for the AI layer to analyze.
    # ------------------------------------------------------------------

    @staticmethod
    def detect_psychological_patterns(
        positions: list,
        all_trades: list | None = None,
    ) -> list[PatternResult]:
        """Detect potential psychological patterns as AI推测 suggestions.

        Unlike tag_position() which produces observable behavior tags,
        these are inferences about trader psychology. They should be
        presented as suggestions, not definitive labels.

        Args:
            positions: All positions in the analysis period.
            all_trades: Raw trade records (optional, enhances detection).

        Returns:
            List of PatternResult instances for psychological patterns.
        """
        results: list[PatternResult] = []

        if not positions:
            return results

        # --- REVENGE: new trade within 24h of significant loss ---
        for pos in positions:
            prior_positions = sorted(
                [p for p in positions if p.exit_date < pos.entry_date],
                key=lambda p: p.exit_date,
            )
            if prior_positions:
                last_prior = prior_positions[-1]
                if last_prior.pnl < 0 and (pos.entry_date - last_prior.exit_date).days <= 1:
                    losing_positions = [p for p in positions if p.pnl < 0]
                    if losing_positions:
                        avg_loss = sum(abs(p.pnl) for p in losing_positions) / len(losing_positions)
                        if abs(last_prior.pnl) > avg_loss * 1.5 and pos.total_quantity > last_prior.total_quantity:
                            results.append(
                                PatternResult(
                                    "REVENGE",
                                    0.5,  # lower confidence for AI suggestion
                                    {
                                        "prior_pnl": last_prior.pnl,
                                        "prior_exit": str(last_prior.exit_date),
                                        "gap_days": (pos.entry_date - last_prior.exit_date).days,
                                    },
                                )
                            )

        # --- OVERTRADING: daily frequency > 95th percentile ---
        if len(positions) >= 20:
            date_counts = Counter(p.entry_date for p in positions)
            daily_counts = list(date_counts.values())
            if len(daily_counts) >= 20:
                p95 = sorted(daily_counts)[int(len(daily_counts) * 0.95)]
                for pos in positions:
                    if date_counts[pos.entry_date] > p95:
                        results.append(
                            PatternResult(
                                "OVERTRADING",
                                0.5,
                                {
                                    "positions_today": date_counts[pos.entry_date],
                                    "total_positions": len(positions),
                                    "trading_days": len(daily_counts),
                                    "p95_threshold": p95,
                                },
                            )
                        )

        # --- HOLD_LOSER / CUT_WINNER: median holding duration comparison ---
        winners = [p for p in positions if p.pnl > 0]
        losers = [p for p in positions if p.pnl < 0]
        if len(winners) >= 5 and len(losers) >= 5:
            median_hold_winners = median(p.holding_days for p in winners)
            median_hold_losers = median(p.holding_days for p in losers)

            for pos in positions:
                if median_hold_losers > median_hold_winners * 1.5 and pos.pnl < 0 and pos.holding_days > median_hold_losers:
                    results.append(
                        PatternResult(
                            "HOLD_LOSER",
                            0.5,
                            {
                                "holding_days": pos.holding_days,
                                "median_holding_winners": median_hold_winners,
                                "median_holding_losers": median_hold_losers,
                            },
                        )
                    )

                if median_hold_winners < median_hold_losers * 0.5 and pos.pnl > 0 and pos.holding_days < median_hold_winners:
                    results.append(
                        PatternResult(
                            "CUT_WINNER",
                            0.5,
                            {
                                "holding_days": pos.holding_days,
                                "median_holding_winners": median_hold_winners,
                                "median_holding_losers": median_hold_losers,
                            },
                        )
                    )

        # --- FOMO (simplified, trade-based only) ---
        if all_trades is not None and len(all_trades) >= 10:
            for pos in positions:
                symbol_trades = sorted(
                    [t for t in all_trades if t.symbol == pos.symbol],
                    key=lambda t: t.datetime,
                )
                if len(symbol_trades) >= 5:
                    entry_trades = [t for t in symbol_trades if t.side == "BUY" and t.datetime.date() <= pos.entry_date]
                    if len(entry_trades) >= 3:
                        prices = [t.price for t in entry_trades[-3:]]
                        if all(prices[i] < prices[i + 1] for i in range(len(prices) - 1)):
                            results.append(
                                PatternResult(
                                    "FOMO",
                                    0.4,
                                    {
                                        "consecutive_buy_price_increase": True,
                                        "recent_prices": prices,
                                    },
                                )
                            )

        return results


# -- helpers ----------------------------------------------------------------


def _maybe_ma_tag(
    tags: list[PatternResult],
    day_data: dict,
    name: str,
    predicate,
) -> None:
    """Append a trend/counter-trend tag if both MAs exist and predicate holds."""
    ma20 = day_data.get("ma20")
    ma60 = day_data.get("ma60")
    if ma20 is not None and ma60 is not None and predicate(ma20, ma60):
        tags.append(
            PatternResult(
                name, 0.7, {"ma20": ma20, "ma60": ma60}
            )
        )
