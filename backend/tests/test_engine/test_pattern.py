"""Tests for pattern engine -- behavioral tags."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.engine.pattern import PatternEngine, PatternResult

# ============================================================================
# Test data notes for some psychological tests:
# - OVERTRADING uses avg + 2*std >= 5 rather than global 95th percentile.
# - PSY_FOMO (0.3) replaces old FOMO (0.4) in detect_psychological_patterns.
# - POSSIBLE_REVENGE (0.3) replaces old REVENGE (0.5).


# -- helpers ----------------------------------------------------------------


@dataclass
class _Position:
    """Minimal position-like object for testing patterns."""

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
    trade_ids: list[str] = field(default_factory=lambda: ["t1", "t2"])
    cost_known: bool = True


@dataclass
class _Trade:
    """Minimal trade-like object for testing pattern detection."""
    symbol: str = "000001"
    side: str = "BUY"
    datetime: datetime = datetime(2024, 1, 2, 9, 30)
    price: float = 0.0


def make_pos(
    holding_days: int = 8,
    pnl_pct: float = 0.1,
    symbol: str = "000001",
    entry_date: date | None = None,
    exit_date: date | None = None,
    avg_entry_price: float = 10.0,
) -> _Position:
    """Create a test position with derived fields."""
    if entry_date is None:
        entry_date = date(2024, 1, 2)
    if exit_date is None:
        exit_date = entry_date + timedelta(days=holding_days)
    avg_entry = avg_entry_price
    avg_exit = round(avg_entry * (1 + pnl_pct), 4)
    qty = 100
    return _Position(
        symbol=symbol,
        asset_type="stock",
        entry_date=entry_date,
        exit_date=exit_date,
        holding_days=holding_days,
        total_quantity=qty,
        avg_entry_price=avg_entry,
        avg_exit_price=avg_exit,
        pnl=round((avg_exit - avg_entry) * qty, 4),
        pnl_pct=pnl_pct,
    )


def tag_names(pos, all_positions=None, **kwargs) -> set[str]:
    """Convenience: return set of tag names for a position."""
    if all_positions is None:
        all_positions = [pos]
    return {t.pattern_name for t in PatternEngine.tag_position(pos, all_positions, **kwargs)}


def _make_market_data(
    dates: list[str],
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    ma20: float | None = 11.0,
    ma60: float | None = 10.0,
    ma5: float | None = None,
    ma10: float | None = None,
    volume: list[float] | None = None,
    avg_volume_20d: float | None = None,
) -> dict:
    """Build market-data dict for one symbol, with optional volume data."""
    if highs is None:
        highs = [c * 1.02 for c in closes]
    if lows is None:
        lows = [c * 0.98 for c in closes]
    data = {}
    for i, d in enumerate(dates):
        entry = {
            "open": closes[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "ma5": ma5 if ma5 is not None else closes[i],
            "ma10": ma10 if ma10 is not None else closes[i],
            "ma20": ma20 if ma20 is not None else closes[i],
            "ma60": ma60 if ma60 is not None else closes[i],
        }
        if volume is not None:
            entry["volume"] = volume[i]
        if avg_volume_20d is not None:
            entry["avg_volume_20d"] = avg_volume_20d
        data[d] = entry
    return {"000001": data}


def _market_tags(pos, market_data) -> set[str]:
    return {t.pattern_name for t in PatternEngine.tag_market_patterns(pos, market_data)}


# ============================================================================
# Module 2 -- Holding period
# ============================================================================


class TestScalpTag:
    def test_holding_less_than_3(self):
        pos = make_pos(holding_days=1)
        tags = tag_names(pos)
        assert "SCALP" in tags
        assert "SWING" not in tags
        assert "POSITION" not in tags

    def test_holding_2_days(self):
        pos = make_pos(holding_days=2)
        assert "SCALP" in tag_names(pos)

    def test_confidence_is_one(self):
        pos = make_pos(holding_days=1)
        results = PatternEngine.tag_position(pos, [pos])
        for r in results:
            if r.pattern_name == "SCALP":
                assert r.confidence == 1.0


class TestSwingTag:
    def test_holding_3_days(self):
        pos = make_pos(holding_days=3)
        tags = tag_names(pos)
        assert "SWING" in tags
        assert "SCALP" not in tags

    def test_holding_30_days(self):
        pos = make_pos(holding_days=30)
        assert "SWING" in tag_names(pos)

    def test_confidence_is_one(self):
        pos = make_pos(holding_days=10)
        results = PatternEngine.tag_position(pos, [pos])
        for r in results:
            if r.pattern_name == "SWING":
                assert r.confidence == 1.0


class TestPositionTag:
    def test_holding_greater_than_30(self):
        pos = make_pos(holding_days=31)
        tags = tag_names(pos)
        assert "POSITION" in tags
        assert "SWING" not in tags

    def test_confidence_is_one(self):
        pos = make_pos(holding_days=45)
        results = PatternEngine.tag_position(pos, [pos])
        for r in results:
            if r.pattern_name == "POSITION":
                assert r.confidence == 1.0


# ============================================================================
# Module 3 -- Risk & position management
# ============================================================================


class TestClassifyPnlLevel:
    """PatternEngine.classify_pnl_level() produces PnL-magnitude buckets, not behavior tags."""

    def test_da_ying(self):
        pos = make_pos(pnl_pct=0.25, holding_days=10)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "大盈"

    def test_zhengchang_yingli(self):
        pos = make_pos(pnl_pct=0.10, holding_days=8)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "正常盈利"

    def test_zhengchang_yingli_boundary_lower(self):
        pos = make_pos(pnl_pct=0.05, holding_days=5)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "正常盈利"

    def test_zhengchang_yingli_boundary_upper(self):
        pos = make_pos(pnl_pct=0.20, holding_days=8)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "正常盈利"

    def test_xiao_ying(self):
        pos = make_pos(pnl_pct=0.03, holding_days=2)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "小盈"

    def test_xiao_kui(self):
        pos = make_pos(pnl_pct=-0.05, holding_days=5)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "小亏"

    def test_xiao_kui_at_boundary(self):
        pos = make_pos(pnl_pct=-0.08, holding_days=3)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "小亏"

    def test_da_kui(self):
        pos = make_pos(pnl_pct=-0.25, holding_days=5)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "大亏"

    def test_da_kui_beyond_eight(self):
        pos = make_pos(pnl_pct=-0.09, holding_days=5)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] == "大亏"

    def test_zero_pnl_has_no_level(self):
        pos = make_pos(pnl_pct=0.0, holding_days=1)
        result = PatternEngine.classify_pnl_level(pos)
        assert result["level"] is None

    def test_pnl_level_not_in_tag_position(self):
        """PnL level buckets should NOT appear in tag_position() results."""
        pos = make_pos(pnl_pct=0.25, holding_days=10)
        tags = tag_names(pos)
        assert "大盈" not in tags
        assert "正常盈利" not in tags
        assert "小盈" not in tags
        assert "小亏" not in tags
        assert "大亏" not in tags


class TestTurnTag:
    def test_same_day_entry_exit_fallback(self):
        """Same-day entry/exit with multiple sibling positions gets TURN (fallback)."""
        d = date(2024, 1, 2)
        p1 = make_pos(holding_days=0, entry_date=d, exit_date=d, pnl_pct=0.01)
        p2 = make_pos(holding_days=0, entry_date=d, exit_date=d, pnl_pct=0.02)
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "TURN" in tags

    def test_same_day_single_position_no_turn_fallback(self):
        """Single same-day position without trades param should NOT get TURN (needs same_ep > 1)."""
        d = date(2024, 1, 2)
        pos = make_pos(holding_days=0, entry_date=d, exit_date=d)
        tags = tag_names(pos, all_positions=[pos])
        assert "TURN" not in tags

    def test_not_tagged_for_multi_day(self):
        pos = make_pos(holding_days=5)
        assert "TURN" not in tag_names(pos)

    def test_confidence_point_seven(self):
        d = date(2024, 1, 2)
        p1 = make_pos(holding_days=0, entry_date=d, exit_date=d, pnl_pct=0.01)
        p2 = make_pos(holding_days=0, entry_date=d, exit_date=d, pnl_pct=0.02)
        results = PatternEngine.tag_position(p2, [p1, p2])
        for r in results:
            if r.pattern_name == "TURN":
                assert r.confidence == 0.7

    def test_trades_with_both_sides_gets_turn(self):
        """Trades with same symbol and date having both BUY/SELL gets TURN."""
        d = date(2024, 1, 2)
        pos = make_pos(holding_days=5, entry_date=d, exit_date=date(2024, 1, 7))
        trades = [
            _Trade(symbol="000001", side="BUY", datetime=datetime(d.year, d.month, d.day)),
            _Trade(symbol="000001", side="SELL", datetime=datetime(d.year, d.month, d.day)),
        ]
        tags = tag_names(pos, all_positions=[pos], trades=trades)
        assert "TURN" in tags

    def test_trades_no_opposite_side_no_turn(self):
        """Trades with only BUY side should NOT get TURN."""
        d = date(2024, 1, 2)
        pos = make_pos(holding_days=5, entry_date=d, exit_date=date(2024, 1, 7))
        trades = [
            _Trade(symbol="000001", side="BUY", datetime=datetime(d.year, d.month, d.day)),
        ]
        tags = tag_names(pos, all_positions=[pos], trades=trades)
        assert "TURN" not in tags


class TestPyramidTag:
    """PYRAMID: adding to a position at a HIGHER price, with time separation >= 1 day."""

    def test_position_higher_price_with_gap_gets_pyramid(self):
        """Position with higher entry price than first position of same symbol and 1+ day gap gets PYRAMID."""
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)  # 3 days later
        p1 = make_pos(avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=10.5, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        # avg_entry_price 10.5 > 10.0 * 1.02 = 10.2, gap = 3 days >= 1
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "PYRAMID" in tags

    def test_same_date_no_pyramid(self):
        """Zero day gap should NOT get PYRAMID."""
        d = date(2024, 1, 2)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d, exit_date=d + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=10.5, entry_date=d, exit_date=d + timedelta(days=5), holding_days=5)
        # gap = 0 days, fails >= 1
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "PYRAMID" not in tags

    def test_price_not_high_enough_no_pyramid(self):
        """Price increase less than 2% should NOT get PYRAMID."""
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=10.15, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        # 10.15 < 10.0 * 1.02 = 10.2, fails
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "PYRAMID" not in tags

    def test_first_position_no_pyramid(self):
        """The first position for a symbol should never get PYRAMID."""
        d = date(2024, 1, 2)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d, exit_date=d + timedelta(days=3), holding_days=3)
        tags = tag_names(p1, all_positions=[p1])
        assert "PYRAMID" not in tags

    def test_confidence_point_eight(self):
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=10.5, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        results = PatternEngine.tag_position(p2, [p1, p2])
        for r in results:
            if r.pattern_name == "PYRAMID":
                assert r.confidence == 0.8


class TestAverageDownTag:
    """AVERAGE_DOWN: adding to a position at a significantly LOWER price (>= 5% lower)."""

    def test_lower_price_gets_average_down(self):
        """Position with entry price at least 5% lower than first position of same symbol gets AVERAGE_DOWN."""
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=9.4, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        # 9.4 < 10.0 * 0.95 = 9.5, qualifies
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "AVERAGE_DOWN" in tags

    def test_price_not_low_enough_no_average_down(self):
        """Price decline less than 5% should NOT get AVERAGE_DOWN."""
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=9.6, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        # 9.6 > 10.0 * 0.95 = 9.5, fails
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "AVERAGE_DOWN" not in tags

    def test_higher_price_not_average_down(self):
        """Higher entry price should NOT get AVERAGE_DOWN."""
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=10.5, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "AVERAGE_DOWN" not in tags

    def test_first_position_no_average_down(self):
        """The first position for a symbol should never get AVERAGE_DOWN."""
        d = date(2024, 1, 2)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d, exit_date=d + timedelta(days=3), holding_days=3)
        tags = tag_names(p1, all_positions=[p1])
        assert "AVERAGE_DOWN" not in tags

    def test_confidence_point_eight(self):
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)
        p1 = make_pos(avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(avg_entry_price=9.4, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        results = PatternEngine.tag_position(p2, [p1, p2])
        for r in results:
            if r.pattern_name == "AVERAGE_DOWN":
                assert r.confidence == 0.8


class TestCashTag:
    def test_first_position_in_period(self):
        pos = make_pos()
        results = PatternEngine.detect_cooldowns(pos, [pos])
        names = {r.pattern_name for r in results}
        assert "CASH" in names

    def test_gap_over_30_days(self):
        p1 = make_pos(holding_days=5, entry_date=date(2024, 1, 2), exit_date=date(2024, 1, 7))
        p2 = make_pos(holding_days=5, entry_date=date(2024, 2, 10), exit_date=date(2024, 2, 15))
        # gap = (2024-02-10) - (2024-01-07) = 34 days > 30
        results = PatternEngine.detect_cooldowns(p2, [p1, p2])
        names = {r.pattern_name for r in results}
        assert "CASH" in names

    def test_no_gap_no_cash(self):
        p1 = make_pos(holding_days=5, entry_date=date(2024, 1, 2), exit_date=date(2024, 1, 7))
        p2 = make_pos(holding_days=5, entry_date=date(2024, 1, 10), exit_date=date(2024, 1, 15))
        # gap = (2024-01-10) - (2024-01-07) = 3 days <= 30
        results = PatternEngine.detect_cooldowns(p2, [p1, p2])
        names = {r.pattern_name for r in results}
        assert "CASH" not in names

    def test_not_emitted_from_tag_position(self):
        """CASH should NOT appear in tag_position() output."""
        pos = make_pos()
        tags = PatternEngine.tag_position(pos, [pos])
        assert "CASH" not in {t.pattern_name for t in tags}


# ============================================================================
# Module 1 -- Market-dependent entry/exit patterns
# ============================================================================


class TestChaseTag:
    def test_chase_detected(self):
        """Entry close > 15% above 5-days-ago close."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]  # 2..26 = 25 days
        closes = [10.0] * 24 + [11.6]  # entry day (idx 24) close = 11.6 >= +16%
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, ma20=10.0)  # ma20=10 so 11.6 > 10*1.10=11.0
        assert "CHASE" in _market_tags(pos, md)

    def test_not_chase_when_flat(self):
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 25
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes)
        assert "CHASE" not in _market_tags(pos, md)

    def test_not_chase_when_dropping(self):
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 20 + [9.0] * 5
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes)
        assert "CHASE" not in _market_tags(pos, md)

    def test_chase_full_confidence(self):
        """All conditions met (5d return, MA deviation, high proximity) -> 0.7."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        # entry_close=13.0, 5d return=30%, ma20=11 -> 13>12.1,
        # prev_20d_high=10.2 -> 13>=9.89
        closes = [10.0] * 24 + [13.0]
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes)
        results = PatternEngine.tag_market_patterns(pos, md)
        for r in results:
            if r.pattern_name == "CHASE":
                assert r.confidence == 0.7

    def test_chase_low_confidence_without_ma_deviation(self):
        """Only 5d return holds, MA deviation fails -> 0.5."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        # entry_close=11.6, ma20=11 -> 11.6 > 12.1? No -> MA condition fails
        # prev_20d_high=10.2 -> 11.6 >= 9.89? Yes -> high proximity OK
        closes = [10.0] * 24 + [11.6]
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes)
        results = PatternEngine.tag_market_patterns(pos, md)
        for r in results:
            if r.pattern_name == "CHASE":
                assert r.confidence == 0.5


class TestBottomTag:
    def test_bottom_detected(self):
        """Entry close < 15% below 5-days-ago close, with downtrend."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 20 + [8.4] * 5  # entry day (idx 24) close = 8.4 <= -16%
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, ma20=10.0, ma60=11.0)  # downtrend
        assert "BOTTOM" in _market_tags(pos, md)

    def test_not_bottom_when_flat(self):
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 25
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, ma20=10.0, ma60=11.0)
        assert "BOTTOM" not in _market_tags(pos, md)

    def test_not_bottom_when_uptrend(self):
        """5d drop > 15% but in uptrend (ma20 > ma60) -> no BOTTOM."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 20 + [8.4] * 5
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes)  # default ma20=11, ma60=10 -> uptrend
        assert "BOTTOM" not in _market_tags(pos, md)


class TestBreakoutTag:
    def test_breakout_with_mock_data(self):
        """Entry day close exceeds max of prior 20 days high."""
        # Build 25 trading days
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]  # 2..26 = 25 days
        # Days 0..23 have highs in range 10-11.5
        # Day 24 (entry) close = 12.5 > max prev high = 11.5
        highs = []
        closes = []
        for i in range(24):
            h = 10.0 + (i % 8) * 0.2  # peaks at 11.6
            highs.append(h)
            closes.append(h * 0.98)
        # Entry day
        highs.append(13.0)
        closes.append(12.5)

        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, highs=highs)

        tags = _market_tags(pos, md)
        assert "BREAKOUT" in tags

    def test_breakout_backward_compat_confidence(self):
        """Without volume data, confidence is 0.5 (backward compat)."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        highs = []
        closes = []
        for i in range(24):
            h = 10.0 + (i % 8) * 0.2
            highs.append(h)
            closes.append(h * 0.98)
        highs.append(13.0)
        closes.append(12.5)

        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, highs=highs)
        results = PatternEngine.tag_market_patterns(pos, md)
        for r in results:
            if r.pattern_name == "BREAKOUT":
                assert r.confidence == 0.5

    def test_breakout_with_volume_confirmation(self):
        """Breakout with sufficient volume gets confidence 0.7."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        highs = []
        closes = []
        volumes = []
        for i in range(24):
            h = 10.0 + (i % 8) * 0.2
            highs.append(h)
            closes.append(h * 0.98)
            volumes.append(100000)
        # Entry day
        highs.append(13.0)
        closes.append(12.5)
        volumes.append(300000)  # 300k > 1.5 * 150k = 225k

        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(
            dates, closes, highs=highs,
            volume=volumes, avg_volume_20d=150000.0,
        )
        tags = _market_tags(pos, md)
        assert "BREAKOUT" in tags

        results = PatternEngine.tag_market_patterns(pos, md)
        for r in results:
            if r.pattern_name == "BREAKOUT":
                assert r.confidence == 0.7

    def test_not_breakout_insufficient_volume(self):
        """Price breaks out but volume is insufficient -> no tag."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        highs = []
        closes = []
        volumes = []
        for i in range(24):
            h = 10.0 + (i % 8) * 0.2
            highs.append(h)
            closes.append(h * 0.98)
            volumes.append(100000)
        # Entry day
        highs.append(13.0)
        closes.append(12.5)
        volumes.append(100000)  # 100k < 1.5 * 150k = 225k -> insufficient

        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(
            dates, closes, highs=highs,
            volume=volumes, avg_volume_20d=150000.0,
        )
        assert "BREAKOUT" not in _market_tags(pos, md)


class TestTrendTag:
    def test_trend_when_ma20_above_ma60_and_price_above_ma20(self):
        """ma20 > ma60 and close > ma20 -> TREND."""
        pos = make_pos(entry_date=date(2024, 1, 15))
        # entry_date = Jan 15, which is index 13 in the dates list
        # set entry day close > ma20=11.0
        closes = [10.0] * 13 + [12.0] + [10.0] * 4
        md = _make_market_data(
            [f"2024-01-{d:02d}" for d in range(2, 20)],
            closes,
            ma20=11.0,
            ma60=10.0,
        )
        assert "BULL_TREND" in _market_tags(pos, md)

    def test_not_trend_when_ma20_below_ma60(self):
        pos = make_pos(entry_date=date(2024, 1, 15))
        md = _make_market_data(
            [f"2024-01-{d:02d}" for d in range(2, 20)],
            [10.0] * 18,
            ma20=10.0,
            ma60=11.0,
        )
        assert "BULL_TREND" not in _market_tags(pos, md)

    def test_not_trend_when_price_below_ma20(self):
        """ma20 > ma60 but price below ma20 -> no TREND."""
        pos = make_pos(entry_date=date(2024, 1, 15))
        ma20 = 11.0
        # entry close = 10.0 < ma20 = 11.0 -> price confirmation fails
        md = _make_market_data(
            [f"2024-01-{d:02d}" for d in range(2, 20)],
            [10.0] * 18,
            ma20=ma20,
            ma60=10.0,
        )
        assert "BULL_TREND" not in _market_tags(pos, md)


class TestCounterTrendTag:
    def test_counter_trend_when_ma20_below_ma60_and_price_below_ma20(self):
        """ma20 < ma60 and close < ma20 -> COUNTER_TREND."""
        pos = make_pos(entry_date=date(2024, 1, 15))
        # entry_date = Jan 15 (index 13), set close < ma20=10.0
        closes = [10.0] * 13 + [9.5] + [10.0] * 4
        md = _make_market_data(
            [f"2024-01-{d:02d}" for d in range(2, 20)],
            closes,
            ma20=10.0,
            ma60=11.0,
        )
        assert "BEAR_TREND" in _market_tags(pos, md)

    def test_not_counter_trend_when_ma20_above_ma60(self):
        pos = make_pos(entry_date=date(2024, 1, 15))
        md = _make_market_data(
            [f"2024-01-{d:02d}" for d in range(2, 20)],
            [10.0] * 18,
            ma20=11.0,
            ma60=10.0,
        )
        assert "BEAR_TREND" not in _market_tags(pos, md)

    def test_not_counter_trend_when_price_above_ma20(self):
        """ma20 < ma60 but price above ma20 -> no COUNTER_TREND."""
        pos = make_pos(entry_date=date(2024, 1, 15))
        # entry close = 12.0 > ma20 = 10.0 -> price confirmation fails
        closes = [10.0] * 13 + [12.0] + [10.0] * 4
        md = _make_market_data(
            [f"2024-01-{d:02d}" for d in range(2, 20)],
            closes,
            ma20=10.0,
            ma60=11.0,
        )
        assert "BEAR_TREND" not in _market_tags(pos, md)


class TestBreakdownTag:
    def test_breakdown_on_exit(self):
        """Exit close < min(prev 20 days low)."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 28)]  # 2..27 = 26 days
        # First 25 days: lows stable at ~9.8
        # Day 26 (exit): close = 9.0 < min prev low = 9.8
        lows = [9.8] * 25 + [8.5]
        closes = [10.0] * 25 + [9.0]
        highs = [10.5] * 25 + [9.5]

        pos = make_pos(
            entry_date=date(2024, 1, 2),
            exit_date=date(2024, 1, 27),
            holding_days=25,
        )
        md = _make_market_data(dates, closes, highs=highs, lows=lows)
        assert "BREAKDOWN" in _market_tags(pos, md)

    def test_not_breakdown_when_normal(self):
        dates = [f"2024-01-{d:02d}" for d in range(2, 28)]
        lows = [9.8] * 26
        closes = [10.0] * 26
        pos = make_pos(
            entry_date=date(2024, 1, 2),
            exit_date=date(2024, 1, 27),
            holding_days=25,
        )
        md = _make_market_data(dates, closes, lows=lows)
        assert "BREAKDOWN" not in _market_tags(pos, md)


# ============================================================================
# Phase 3 — FOMO (still in tag_market_patterns, market-data dependent)
# ============================================================================


class TestFomoTag:
    """FOMO: entry near day's high after streak of up days."""

    def test_fomo_detected(self):
        """3+ up days in last 5 and entry near high."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]  # 25 days
        closes = [10.0] * 19 + [10.3, 10.5, 10.8, 11.0, 11.3] + [12.0]
        # 5 up days before entry ✓, entry_close=12.0
        highs = [c * 1.03 for c in closes]
        highs[-1] = 12.1  # 12.0 >= 12.1*0.98=11.858 ✓
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, highs=highs)
        assert "FOMO" in _market_tags(pos, md)

    def test_not_fomo_when_no_up_days(self):
        """Flat before entry -> no FOMO."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 24 + [12.0]
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes)
        assert "FOMO" not in _market_tags(pos, md)

    def test_not_fomo_when_not_near_high(self):
        """Entry not close to day's high -> no FOMO."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 19 + [10.3, 10.5, 10.8, 11.0, 11.3] + [11.5]
        highs = [c * 1.03 for c in closes]
        # entry high = 11.5*1.03=11.845, 11.5 >= 11.845*0.98=11.608? No!
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, highs=highs)
        assert "FOMO" not in _market_tags(pos, md)

    def test_not_fomo_when_insufficient_data(self):
        """Less than 5 days of data -> no FOMO."""
        dates = [f"2024-01-{d:02d}" for d in range(2, 7)]  # 5 days
        closes = [10.0, 10.3, 10.5, 10.8, 11.0]
        pos = make_pos(entry_date=date(2024, 1, 6))
        md = _make_market_data(dates, closes)
        assert "FOMO" not in _market_tags(pos, md)

    def test_fomo_confidence(self):
        dates = [f"2024-01-{d:02d}" for d in range(2, 27)]
        closes = [10.0] * 19 + [10.3, 10.5, 10.8, 11.0, 11.3] + [12.0]
        highs = [c * 1.03 for c in closes]
        highs[-1] = 12.1
        pos = make_pos(entry_date=date(2024, 1, 26))
        md = _make_market_data(dates, closes, highs=highs)
        results = PatternEngine.tag_market_patterns(pos, md)
        for r in results:
            if r.pattern_name == "FOMO":
                assert r.confidence == 0.7


# ============================================================================
# Edge cases
# ============================================================================


class TestNoMarketData:
    def test_empty_market_data_returns_empty(self):
        pos = make_pos()
        assert PatternEngine.tag_market_patterns(pos, {}) == []

    def test_missing_symbol_returns_empty(self):
        pos = make_pos()
        md = {"OTHER": {}}
        assert PatternEngine.tag_market_patterns(pos, md) == []

    def test_missing_entry_date_returns_empty(self):
        pos = make_pos()
        md = {"000001": {"2024-02-01": {"close": 10}}}
        assert PatternEngine.tag_market_patterns(pos, md) == []


class TestTagCoexistence:
    def test_scalp_and_turn_can_coexist(self):
        """A same-day trade with multiple siblings can be both SCALP and TURN."""
        d = date(2024, 1, 2)
        p1 = make_pos(holding_days=0, entry_date=d, exit_date=d, pnl_pct=0.01)
        p2 = make_pos(holding_days=0, entry_date=d, exit_date=d, pnl_pct=0.02)
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "SCALP" in tags
        assert "TURN" in tags

    def test_scalp_and_turn_via_trades(self):
        """A trade can be SCALP and TURN via trades parameter even with single position."""
        d = date(2024, 1, 2)
        pos = make_pos(holding_days=0, entry_date=d, exit_date=d)
        trades = [
            _Trade(symbol="000001", side="BUY", datetime=datetime(d.year, d.month, d.day)),
            _Trade(symbol="000001", side="SELL", datetime=datetime(d.year, d.month, d.day)),
        ]
        tags = tag_names(pos, all_positions=[pos], trades=trades)
        assert "SCALP" in tags
        assert "TURN" in tags

    def test_average_down_with_loss(self):
        """A losing position in a multi-entry day gets AVERAGE_DOWN."""
        d1 = date(2024, 1, 2)
        d2 = date(2024, 1, 5)
        p1 = make_pos(pnl_pct=0.05, avg_entry_price=10.0, entry_date=d1, exit_date=d1 + timedelta(days=3), holding_days=3)
        p2 = make_pos(pnl_pct=-0.05, avg_entry_price=9.4, entry_date=d2, exit_date=d2 + timedelta(days=5), holding_days=5)
        # avg_entry 9.4 < 10.0 * 0.95 = 9.5 -> AVERAGE_DOWN
        tags = tag_names(p2, all_positions=[p1, p2])
        assert "AVERAGE_DOWN" in tags


# ============================================================================
# Phase 4 -- Tag Hierarchy (resolve_hierarchy)
# ============================================================================


class TestResolveHierarchy:
    """Tag hierarchy: L1->L2 via context.sub_pattern."""

    def test_trend_with_breakout_sets_sub_pattern(self):
        tags = [
            PatternResult("BULL_TREND", 0.7, {"ma20": 11, "ma60": 10}),
            PatternResult("BREAKOUT", 0.7, {}),
            PatternResult("SWING", 1.0, {"holding_days": 8}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        trend = next(t for t in result if t.pattern_name == "BULL_TREND")
        assert trend.context.get("sub_pattern") == "BREAKOUT"

    def test_trend_with_chase_sets_sub_pattern(self):
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("CHASE", 0.7, {}),
            PatternResult("SWING", 1.0, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        trend = next(t for t in result if t.pattern_name == "BULL_TREND")
        assert trend.context.get("sub_pattern") == "CHASE"

    def test_trend_breakout_preferred_over_chase(self):
        """BREAKOUT appears first in the hierarchy check, so it wins."""
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("BREAKOUT", 0.7, {}),
            PatternResult("CHASE", 0.7, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        trend = next(t for t in result if t.pattern_name == "BULL_TREND")
        assert trend.context.get("sub_pattern") == "BREAKOUT"

    def test_counter_trend_with_bottom(self):
        tags = [
            PatternResult("BEAR_TREND", 0.7, {}),
            PatternResult("BOTTOM", 0.7, {}),
            PatternResult("SWING", 1.0, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        ct = next(t for t in result if t.pattern_name == "BEAR_TREND")
        assert ct.context.get("sub_pattern") == "BOTTOM"

    def test_counter_trend_with_breakdown(self):
        tags = [
            PatternResult("BEAR_TREND", 0.7, {}),
            PatternResult("BREAKDOWN", 0.7, {}),
            PatternResult("POSITION", 1.0, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        ct = next(t for t in result if t.pattern_name == "BEAR_TREND")
        assert ct.context.get("sub_pattern") == "BREAKDOWN"

    def test_no_hierarchy_change_when_no_related_tags(self):
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("SWING", 1.0, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        trend = next(t for t in result if t.pattern_name == "BULL_TREND")
        assert "sub_pattern" not in trend.context

    def test_no_hierarchy_for_unrelated_tags(self):
        tags = [
            PatternResult("SCALP", 1.0, {}),
            PatternResult("SWING", 1.0, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        assert all("sub_pattern" not in t.context for t in result)

    def test_multiple_trend_tags_all_get_sub_pattern(self):
        """If multiple positions have TREND, all should get sub_pattern."""
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("BREAKOUT", 0.7, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        for t in result:
            if t.pattern_name == "BULL_TREND":
                assert t.context.get("sub_pattern") == "BREAKOUT"

    def test_double_hierarchy(self):
        """TREND+COUNTER_TREND both get their sub_patterns independently."""
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("BEAR_TREND", 0.7, {}),
            PatternResult("BREAKOUT", 0.7, {}),
            PatternResult("BOTTOM", 0.7, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        for t in result:
            if t.pattern_name == "BULL_TREND":
                assert t.context.get("sub_pattern") == "BREAKOUT"
            if t.pattern_name == "BEAR_TREND":
                assert t.context.get("sub_pattern") == "BOTTOM"


# ============================================================================
# P1-6: Psychological Pattern Suggestions (AI推测 layer)
# ============================================================================


class TestDetectPsychologicalPatterns:
    """PatternEngine.detect_psychological_patterns() -- AI suggestion layer."""

    def test_empty_positions_returns_empty(self):
        results = PatternEngine.detect_psychological_patterns([], all_trades=[])
        assert results == []

    def test_possible_revenge_detected(self):
        """POSSIBLE_REVENGE: new trade within 24h of significant loss."""
        # We need 2 losing positions so avg_loss < abs(big_loss)
        positions = [
            make_pos(pnl_pct=-0.1, symbol="S1", holding_days=5,
                     entry_date=date(2024, 1, 2), exit_date=date(2024, 1, 7)),  # small loss
            make_pos(pnl_pct=-0.6, symbol="S1", holding_days=5,
                     entry_date=date(2024, 1, 8), exit_date=date(2024, 1, 13)),  # big loss: -600 PnL
            make_pos(pnl_pct=0.1, symbol="S2", holding_days=3,
                     entry_date=date(2024, 1, 14), exit_date=date(2024, 1, 17)),  # revenge: next day, bigger qty
        ]
        positions[2].total_quantity = 200  # larger than prior (100)
        results = PatternEngine.detect_psychological_patterns(positions)
        names = {r[1].pattern_name for r in results}
        assert "POSSIBLE_REVENGE" in names

    def test_overtrading_detected(self):
        """Overtrading: need >=20 days, one day with count > avg+2*std and >=5."""
        positions = []
        # 20 dates with 1 position each
        for i in range(20):
            positions.append(make_pos(
                pnl_pct=0.01, holding_days=1,
                entry_date=date(2024, 1, 2 + i), exit_date=date(2024, 1, 3 + i)))
        # 1 date with 6 positions (avg ~1.05, std ~1.07, threshold ~3.19, max(3.19,5)=5, 6>5)
        for i in range(6):
            positions.append(make_pos(
                pnl_pct=0.01, holding_days=1,
                entry_date=date(2024, 1, 23), exit_date=date(2024, 1, 24)))
        # total: 20 + 6 = 26 positions, 21 distinct dates
        results = PatternEngine.detect_psychological_patterns(positions)
        names = {r[1].pattern_name for r in results}
        assert "OVERTRADING" in names

    def test_hold_loser_detected(self):
        """Hold loser: losers held significantly longer than winners."""
        positions = []
        # 5 winners, held short (2-3 days)
        for i in range(5):
            positions.append(make_pos(pnl_pct=0.1, holding_days=2 + i % 2,
                                      entry_date=date(2024, 1, 2 + i),
                                      exit_date=date(2024, 1, 4 + i + i % 2)))
        # 5 losers, held long (10-14 days)
        for i in range(5):
            positions.append(make_pos(pnl_pct=-0.05, holding_days=10 + i,
                                      entry_date=date(2024, 1, 10 + i),
                                      exit_date=date(2024, 1, 20 + i)))
        # Winners: holding_days = [2, 3, 2, 3, 2] -> median = 2
        # Losers: holding_days = [10, 11, 12, 13, 14] -> median = 12
        # 12 > 2 * 1.5 = 3 ✓
        # The last loser (holding_days=14) > 12 ✓
        results = PatternEngine.detect_psychological_patterns(positions)
        names = {r[1].pattern_name for r in results}
        assert "HOLD_LOSER" in names

    def test_cut_winner_detected(self):
        """Cut winner: winners held significantly shorter than losers."""
        positions = []
        # 5 winners, held very short (1-3 days), median=2
        for i in range(5):
            positions.append(make_pos(pnl_pct=0.1, holding_days=[1, 1, 2, 2, 3][i],
                                      entry_date=date(2024, 1, 2 + i),
                                      exit_date=date(2024, 2, 1 + i)))
        # 5 losers, held long (8-12 days)
        for i in range(5):
            positions.append(make_pos(pnl_pct=-0.05, holding_days=8 + i,
                                      entry_date=date(2024, 1, 10 + i),
                                      exit_date=date(2024, 1, 18 + i)))
        # Winners: holding_days = [1, 2, 1, 2, 1] -> median = 1
        # Losers: holding_days = [8, 9, 10, 11, 12] -> median = 10
        # 1 < 10 * 0.5 = 5 ✓
        # The first winner (holding_days=1) < 1? No, 1 < 1 is False.
        # Need a winner with holding_days < median_hold_winners
        # Let me adjust: 5 winners [1,1,2,2,3] -> median = 2
        results = PatternEngine.detect_psychological_patterns(positions)
        names = {r[1].pattern_name for r in results}
        assert "CUT_WINNER" in names

    def test_all_psychological_tags_have_low_confidence(self):
        """Psychological tags should have confidence <= 0.5."""
        positions = []
        # 5 winners held short (1-3 days), median=2
        for i in range(5):
            positions.append(make_pos(pnl_pct=0.1, holding_days=[1, 1, 2, 2, 3][i],
                                      entry_date=date(2024, 1, 2 + i),
                                      exit_date=date(2024, 1, 5 + i)))
        # 5 losers held long (10-14 days)
        for i in range(5):
            positions.append(make_pos(pnl_pct=-0.05, holding_days=10 + i,
                                      entry_date=date(2024, 1, 10 + i),
                                      exit_date=date(2024, 1, 20 + i)))
        # 15 extra positions on varied February dates for overtrading context
        for i in range(15):
            positions.append(make_pos(pnl_pct=0.01, holding_days=1,
                                      entry_date=date(2024, 2, 1 + i),
                                      exit_date=date(2024, 2, 2 + i)))
        results = PatternEngine.detect_psychological_patterns(positions)
        for r in results:
            assert r[1].confidence <= 0.5, f"{r[1].pattern_name} has confidence {r[1].confidence} > 0.5"

    def test_psy_fomo_has_lower_confidence(self):
        """PSY_FOMO from detect_psychological_patterns has confidence 0.3."""
        positions = []
        for i in range(10):
            positions.append(make_pos(pnl_pct=0.1, holding_days=1,
                                      entry_date=date(2024, 1, 2 + i),
                                      exit_date=date(2024, 1, 3 + i)))
        trades = [
            _Trade(symbol="S1", side="BUY", datetime=datetime(2024, 1, 5, 9, 30)),
            _Trade(symbol="S1", side="BUY", datetime=datetime(2024, 1, 6, 9, 30)),
            _Trade(symbol="S1", side="BUY", datetime=datetime(2024, 1, 7, 9, 30)),
            _Trade(symbol="S1", side="BUY", datetime=datetime(2024, 1, 8, 9, 30)),
            _Trade(symbol="S1", side="BUY", datetime=datetime(2024, 1, 9, 9, 30)),
        ]
        for t in trades:
            t.price = 10.0
        # First position has 3+ buy trades with increasing prices to trigger PSY_FOMO
        results = PatternEngine.detect_psychological_patterns(positions, all_trades=trades)
        for r in results:
            if r[1].pattern_name == "PSY_FOMO":
                assert r[1].confidence == 0.3

    def test_possible_revenge_confidence(self):
        """POSSIBLE_REVENGE from detect_psychological_patterns has confidence 0.3."""
        positions = [
            make_pos(pnl_pct=-0.1, symbol="S1", holding_days=5,
                     entry_date=date(2024, 1, 2), exit_date=date(2024, 1, 7)),
            make_pos(pnl_pct=-0.6, symbol="S1", holding_days=5,
                     entry_date=date(2024, 1, 8), exit_date=date(2024, 1, 13)),
            make_pos(pnl_pct=0.1, symbol="S2", holding_days=3,
                     entry_date=date(2024, 1, 14), exit_date=date(2024, 1, 17)),
        ]
        positions[2].total_quantity = 200
        results = PatternEngine.detect_psychological_patterns(positions)
        for r in results:
            if r[1].pattern_name == "POSSIBLE_REVENGE":
                assert r[1].confidence == 0.3


# ============================================================================
# Fix 1: Outcome separation — compute_outcome replaces is_outcome flag
# ============================================================================


class TestCategoryField:
    """PatternResult.category is set by resolve_per_category() based on CATEGORY_MAP."""

    def test_category_map_has_all_behavior_tags(self):
        """CATEGORY_MAP covers all behavioral pattern names."""
        expected = {
            "CHASE", "BOTTOM", "BREAKOUT",
            "BULL_TREND", "BEAR_TREND", "SIDEWAYS", "BREAKDOWN",
            "SCALP", "SWING", "POSITION",
            "PYRAMID", "AVERAGE_DOWN", "TURN",
            "TIGHT_STOP", "TRAILING_STOP", "TIME_EXIT", "LARGE_LOSS_EXIT",
            "FOMO",
            "POSSIBLE_REVENGE", "OVERTRADING", "HOLD_LOSER", "CUT_WINNER", "PSY_FOMO",
        }
        assert set(PatternEngine.CATEGORY_MAP.keys()) == expected

    def test_resolve_per_category_keeps_highest_confidence(self):
        tags = [
            PatternResult("CHASE", 0.5, {}),
            PatternResult("FOMO", 0.7, {}),
            PatternResult("SWING", 1.0, {}),
        ]
        result = PatternEngine.resolve_per_category(tags)
        result_by_name = {r.pattern_name: r for r in result}
        # CHASE, FOMO, SWING all in behavior -> SWING (1.0) wins
        assert "SWING" in result_by_name
        assert "CHASE" not in result_by_name
        assert "FOMO" not in result_by_name
        assert result_by_name["SWING"].category == "behavior"

    def test_resolve_per_category_different_categories_all_kept(self):
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),   # market_env
            PatternResult("SWING", 1.0, {}),          # behavior
            PatternResult("TIGHT_STOP", 0.8, {}),     # outcome
        ]
        result = PatternEngine.resolve_per_category(tags)
        assert len(result) == 3

    def test_resolve_per_category_empty_returns_empty(self):
        assert PatternEngine.resolve_per_category([]) == []

    def test_resolve_per_category_same_category_only_highest(self):
        """Only the highest confidence tag per category survives."""
        tags = [
            PatternResult("SCALP", 1.0, {}),    # behavior
            PatternResult("SWING", 0.8, {}),    # behavior
            PatternResult("POSITION", 0.6, {}), # behavior
        ]
        result = PatternEngine.resolve_per_category(tags)
        assert len(result) == 1
        assert result[0].pattern_name == "SCALP"
        assert result[0].category == "behavior"

    def test_psychological_tags_in_category_map(self):
        """Psychological tags ARE in CATEGORY_MAP under 'psychology' dimension."""
        for tag in ("PSY_FOMO", "POSSIBLE_REVENGE", "OVERTRADING"):
            assert tag in PatternEngine.CATEGORY_MAP
            assert PatternEngine.CATEGORY_MAP[tag] == "psychology"


# ============================================================================
# Fix 5: resolve_hierarchy actually removes CHASE when BREAKOUT is present
# ============================================================================


class TestResolveHierarchyDedup:
    """Fix 5: resolve_hierarchy must REMOVE CHASE when BREAKOUT is also present."""

    def test_chase_removed_when_breakout_present(self):
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("BREAKOUT", 0.7, {}),
            PatternResult("CHASE", 0.5, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        names = {t.pattern_name for t in result}
        assert "BREAKOUT" in names
        assert "CHASE" not in names

    def test_chase_kept_when_breakout_absent(self):
        """CHASE should remain if no BREAKOUT is present."""
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("CHASE", 0.5, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        names = {t.pattern_name for t in result}
        assert "CHASE" in names

    def test_trend_breakout_preferred_over_chase_removes_chase(self):
        """BREAKOUT removes CHASE; TREND gets sub_pattern=BREAKOUT."""
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("BREAKOUT", 0.7, {}),
            PatternResult("CHASE", 0.5, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        names = {t.pattern_name for t in result}
        assert "CHASE" not in names
        assert "BREAKOUT" in names
        trend = next(t for t in result if t.pattern_name == "BULL_TREND")
        assert trend.context.get("sub_pattern") == "BREAKOUT"

    def test_chase_removed_but_other_tags_kept(self):
        tags = [
            PatternResult("BULL_TREND", 0.7, {}),
            PatternResult("BREAKOUT", 0.7, {}),
            PatternResult("CHASE", 0.5, {}),
            PatternResult("SWING", 1.0, {}),
        ]
        result = PatternEngine.resolve_hierarchy(tags)
        names = {t.pattern_name for t in result}
        assert "BREAKOUT" in names
        assert "CHASE" not in names
        assert "BULL_TREND" in names
        assert "SWING" in names


# ============================================================================
# Fix 6: Exit pattern dimension -- new exit tags in tag_position()
# ============================================================================


class TestTightStopTag:
    """TIGHT_STOP: loss -2% to -5% within 3 days."""

    def test_qualifying_loss_gets_tight_stop(self):
        pos = make_pos(pnl_pct=-0.03, holding_days=2)
        assert "TIGHT_STOP" in tag_names(pos)

    def test_at_boundary_minus_five(self):
        pos = make_pos(pnl_pct=-0.05, holding_days=1)
        assert "TIGHT_STOP" in tag_names(pos)

    def test_at_boundary_minus_two(self):
        pos = make_pos(pnl_pct=-0.02, holding_days=3)
        assert "TIGHT_STOP" in tag_names(pos)

    def test_not_when_held_too_long(self):
        """Loss within -2% to -5% but held > 3 days should NOT get TIGHT_STOP."""
        pos = make_pos(pnl_pct=-0.03, holding_days=4)
        assert "TIGHT_STOP" not in tag_names(pos)

    def test_not_when_loss_too_large(self):
        pos = make_pos(pnl_pct=-0.06, holding_days=2)
        assert "TIGHT_STOP" not in tag_names(pos)

    def test_not_when_profitable(self):
        pos = make_pos(pnl_pct=0.02, holding_days=2)
        assert "TIGHT_STOP" not in tag_names(pos)

    def test_confidence(self):
        pos = make_pos(pnl_pct=-0.03, holding_days=2)
        results = PatternEngine.tag_position(pos, [pos])
        for r in results:
            if r.pattern_name == "TIGHT_STOP":
                assert r.confidence == 0.8


class TestTrailingStopTag:
    """TRAILING_STOP: held > 10 days, exited with profit 0-10%."""

    def test_qualifying_profit_gets_trailing_stop(self):
        pos = make_pos(pnl_pct=0.05, holding_days=15)
        assert "TRAILING_STOP" in tag_names(pos)

    def test_at_upper_boundary(self):
        pos = make_pos(pnl_pct=0.10, holding_days=11)
        assert "TRAILING_STOP" in tag_names(pos)

    def test_not_when_held_short(self):
        pos = make_pos(pnl_pct=0.05, holding_days=10)
        assert "TRAILING_STOP" not in tag_names(pos)

    def test_not_when_profit_too_large(self):
        pos = make_pos(pnl_pct=0.12, holding_days=15)
        assert "TRAILING_STOP" not in tag_names(pos)

    def test_not_when_losing(self):
        pos = make_pos(pnl_pct=-0.05, holding_days=15)
        assert "TRAILING_STOP" not in tag_names(pos)

    def test_confidence(self):
        pos = make_pos(pnl_pct=0.05, holding_days=15)
        results = PatternEngine.tag_position(pos, [pos])
        for r in results:
            if r.pattern_name == "TRAILING_STOP":
                assert r.confidence == 0.6


class TestTimeExitTag:
    """TIME_EXIT: held > 30 days, absolute PnL < 5%."""

    def test_qualifying_gets_time_exit(self):
        pos = make_pos(pnl_pct=-0.03, holding_days=35)
        assert "TIME_EXIT" in tag_names(pos)

    def test_with_small_profit(self):
        pos = make_pos(pnl_pct=0.04, holding_days=40)
        assert "TIME_EXIT" in tag_names(pos)

    def test_at_boundary(self):
        pos = make_pos(pnl_pct=0.049, holding_days=31)
        assert "TIME_EXIT" in tag_names(pos)

    def test_not_when_pnl_too_large(self):
        pos = make_pos(pnl_pct=0.06, holding_days=35)
        assert "TIME_EXIT" not in tag_names(pos)

    def test_not_when_held_short(self):
        pos = make_pos(pnl_pct=0.03, holding_days=30)
        assert "TIME_EXIT" not in tag_names(pos)

    def test_confidence(self):
        pos = make_pos(pnl_pct=-0.03, holding_days=35)
        results = PatternEngine.tag_position(pos, [pos])
        for r in results:
            if r.pattern_name == "TIME_EXIT":
                assert r.confidence == 0.6


class TestPanicExitTag:
    """LARGE_LOSS_EXIT: loss > 20%."""

    def test_qualifying_loss_gets_panic_exit(self):
        pos = make_pos(pnl_pct=-0.25, holding_days=5)
        assert "LARGE_LOSS_EXIT" in tag_names(pos)

    def test_at_boundary(self):
        pos = make_pos(pnl_pct=-0.21, holding_days=3)
        assert "LARGE_LOSS_EXIT" in tag_names(pos)

    def test_not_when_loss_small(self):
        pos = make_pos(pnl_pct=-0.19, holding_days=5)
        assert "LARGE_LOSS_EXIT" not in tag_names(pos)

    def test_not_when_profitable(self):
        pos = make_pos(pnl_pct=0.05, holding_days=5)
        assert "LARGE_LOSS_EXIT" not in tag_names(pos)

    def test_confidence(self):
        pos = make_pos(pnl_pct=-0.30, holding_days=5)
        results = PatternEngine.tag_position(pos, [pos])
        for r in results:
            if r.pattern_name == "LARGE_LOSS_EXIT":
                assert r.confidence == 0.9
