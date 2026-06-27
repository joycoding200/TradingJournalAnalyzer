"""Tests for analysis API endpoints (run, stats, insight, whatif)."""

import pytest

from app.models.analysis import Analysis

QMT_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,平安银行,买入,10.50,1000,5.00\n"
    "2024-01-08 14:00:00,000001,平安银行,卖出,11.00,1000,5.00\n"
    "2024-02-01 09:30:00,600001,包钢股份,买入,5.00,2000,3.00\n"
    "2024-02-05 14:00:00,600001,包钢股份,卖出,4.65,2000,3.00"
)

TEST_EMAIL = "analysis_api_test@test.com"
TEST_PASSWORD = "secret123"


def get_auth_header(client, email=TEST_EMAIL):
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def import_trades(client, headers):
    """Helper: upload, confirm, and import QMT trades. Returns raw_file_id."""
    r = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("trades.csv", QMT_CSV, "text/csv")},
    )
    raw_file_id = r.json()["raw_file_id"]
    client.post(
        "/api/upload/confirm",
        headers=headers,
        json={"raw_file_id": raw_file_id, "source_type": "smart"},
    )
    client.post(
        "/api/upload/import",
        headers=headers,
        json={"raw_file_id": raw_file_id},
    )
    return raw_file_id


def run_analysis(
    client,
    headers,
    date_start="2024-01-01",
    date_end="2024-12-31",
    raw_file_id="",
):
    """Helper: create an analysis bound to a raw file and return its id.

    An analysis is always tied to one uploaded file in the real Upload flow;
    passing raw_file_id keeps the test honest about that boundary.
    """
    resp = client.post(
        "/api/analysis/run",
        headers=headers,
        json={
            "date_start": date_start,
            "date_end": date_end,
            "raw_file_id": raw_file_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()["analysis_id"]


class TestAnalysisRun:
    """Test creating an analysis."""

    def test_run_analysis_creates_record(self, client):
        headers = get_auth_header(client)
        analysis_id = run_analysis(client, headers)
        assert len(analysis_id) > 0

    def test_run_analysis_requires_auth(self, client):
        resp = client.post(
            "/api/analysis/run",
            json={"date_start": "2024-01-01", "date_end": "2024-12-31"},
        )
        assert resp.status_code == 403


class _BaseAnalysisTest:
    """Base class with setup that registers a user, imports trades, creates analysis."""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.headers = get_auth_header(client)
        self.raw_file_id = import_trades(client, self.headers)
        self.analysis_id = run_analysis(
            client, self.headers, raw_file_id=self.raw_file_id
        )


class TestAnalysisStats(_BaseAnalysisTest):
    """Test the stats endpoint."""

    def test_stats_returns_kpis(self, client):
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trades"] == 4
        assert data["total_positions"] == 2
        assert data["win_count"] == 1
        assert data["win_rate"] == 0.5
        # Gross PnL = 500 - 700 = -200; net of commissions (5+5+3+3 = 16) = -216.
        # PnL deducts both-side fees per project convention (see PROJECT_EXPERIENCE.md).
        assert data["total_pnl"] == -216.0
        assert data["avg_holding_days"] == 3.5
        # Per-position PnL is also net of both-side commissions:
        #   平安银行 gross +500, fees 5+5=10 → 490
        #   包钢股份 gross -700, fees 3+3=6  → -706
        assert data["max_win"] == 490.0
        assert data["max_loss"] == -706.0
        assert data["consecutive_losses"] == 1
        assert len(data["positions"]) == 2

    def test_stats_without_trades(self, client):
        """Analysis with no trades should return zeros."""
        # Use same user but a date range with no trades
        resp = client.post(
            "/api/analysis/run",
            headers=self.headers,
            json={"date_start": "2023-01-01", "date_end": "2023-01-31"},
        )
        aid = resp.json()["analysis_id"]
        resp = client.get(
            f"/api/analysis/{aid}/stats",
            headers=self.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trades"] == 0
        assert data["total_positions"] == 0
        assert data["total_pnl"] == 0.0

    def test_stats_404_for_nonexistent_analysis(self, client):
        headers = get_auth_header(client, "nonexistent_stats@test.com")
        resp = client.get(
            "/api/analysis/nonexistent-id/stats",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_stats_requires_auth(self, client):
        client.cookies.clear()  # clear auth cookie set by setup fixture
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
        )
        assert resp.status_code == 403


# CSV variants for degenerate-path coverage (P0 / P1a regression tests).
ALL_LOSS_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,亏损A,买入,10.00,1000,5.00\n"
    "2024-01-08 14:00:00,000001,亏损A,卖出,9.00,1000,5.00\n"
    "2024-02-01 09:30:00,600001,亏损B,买入,5.00,2000,3.00\n"
    "2024-02-05 14:00:00,600001,亏损B,卖出,4.50,2000,3.00"
)

ALL_WIN_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,盈利A,买入,10.00,1000,5.00\n"
    "2024-01-08 14:00:00,000001,盈利A,卖出,11.00,1000,5.00\n"
    "2024-02-01 09:30:00,600001,盈利B,买入,5.00,2000,3.00\n"
    "2024-02-05 14:00:00,600001,盈利B,卖出,5.50,2000,3.00"
)


def _import_csv(client, headers, csv_content: str) -> str:
    """Upload + confirm + import an arbitrary QMT-format CSV. Returns raw_file_id."""
    r = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("trades.csv", csv_content, "text/csv")},
    )
    raw_file_id = r.json()["raw_file_id"]
    client.post(
        "/api/upload/confirm",
        headers=headers,
        json={"raw_file_id": raw_file_id, "source_type": "smart"},
    )
    client.post(
        "/api/upload/import",
        headers=headers,
        json={"raw_file_id": raw_file_id},
    )
    return raw_file_id


class TestDegeneratePaths:
    """Regression tests for the two degenerate paths flagged in metrics review.

    - 全程亏损 (never a winning trade): max_drawdown_pct must NOT collapse to 0.
    - 100% 胜率 (no losing trade): profit_factor / win_loss_ratio must be null
      (rendered as ∞), not 0.0.
    """

    def test_all_losing_max_drawdown_pct_nonzero(self, client):
        """P0: an account that loses from trade one must report a real DD%."""
        headers = get_auth_header(client, "all_loss@test.com")
        raw_file_id = _import_csv(client, headers, ALL_LOSS_CSV)
        aid = run_analysis(client, headers, raw_file_id=raw_file_id)
        resp = client.get(f"/api/analysis/{aid}/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Both positions lost → cumulative PnL never turns positive, so the
        # pre-fix code pathed through `peak == 0` and reported DD% = 0. The
        # fix falls back to total_invested as the denominator.
        assert data["loss_count"] == 2
        assert data["total_pnl"] < 0
        assert data["max_drawdown"] > 0
        assert data["max_drawdown_pct"] > 0, (
            "全程亏损场景下最大回撤百分比不应为 0（P0 回归）"
        )
        # consecutive_losses should count both (pnl <= 0 unification, P2b)
        assert data["consecutive_losses"] == 2

    def test_all_winning_profit_factor_is_null(self, client):
        """P1a: 100% win rate → PF / Payoff are undefined, not 0.0."""
        headers = get_auth_header(client, "all_win@test.com")
        raw_file_id = _import_csv(client, headers, ALL_WIN_CSV)
        aid = run_analysis(client, headers, raw_file_id=raw_file_id)
        resp = client.get(f"/api/analysis/{aid}/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["loss_count"] == 0
        assert data["win_count"] == 2
        assert data["win_rate"] == 1.0
        # Undefined, not "unqualified 0.0". Frontend renders these as ∞.
        assert data["profit_factor"] is None, (
            "无亏损时 profit_factor 应为 null（∞），不是 0.0（P1a 回归）"
        )
        assert data["win_loss_ratio"] is None, (
            "无亏损时 win_loss_ratio 应为 null（∞），不是 0.0（P1a 回归）"
        )
        assert data["consecutive_losses"] == 0


class TestAnalysisInsight(_BaseAnalysisTest):
    """Test the insight endpoint."""

    def test_insight_returns_patterns(self, client):
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/insight",
            headers=self.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["patterns"]) > 0
        pattern_names = {p["pattern_name"] for p in data["patterns"]}
        assert "SWING" in pattern_names
        # best_pattern may be None when sample size < 5 per pattern
        # Each position gets multiple pattern tags (SWING, profit-tags/SMALL_LOSS_EXIT, CASH)
        total_count = sum(p["count"] for p in data["patterns"])
        assert total_count > 0

    def test_insight_best_and_worst_pattern(self, client):
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/insight",
            headers=self.headers,
        )
        data = resp.json()
        # best/worst only set when patterns meet min sample size (count >= 5)
        if data["best_pattern"] is not None:
            if data["worst_pattern"] is not None:
                assert (
                    data["best_pattern"]["total_pnl"]
                    >= data["worst_pattern"]["total_pnl"]
                )

    def test_insight_404_for_nonexistent(self, client):
        headers = get_auth_header(client, "insight_404@test.com")
        resp = client.get(
            "/api/analysis/nonexistent-id/insight",
            headers=headers,
        )
        assert resp.status_code == 404


class TestAnalysisWhatIf(_BaseAnalysisTest):
    """Test the what-if endpoint."""

    def test_whatif_returns_items(self, client):
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/whatif",
            headers=self.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # With primary attribution and small test datasets, items may be empty
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "removed_pattern" in item
            assert "original_return" in item
            assert "what_if_return" in item
            assert "delta" in item

    def test_whatif_404_for_nonexistent(self, client):
        headers = get_auth_header(client, "whatif_404@test.com")
        resp = client.get(
            "/api/analysis/nonexistent-id/whatif",
            headers=headers,
        )
        assert resp.status_code == 404


class TestEquityCurve(_BaseAnalysisTest):
    """V4.0: equity_curve — 按持仓退出日期累计 PnL 的数据点序列。

    领域定义 (CLAUDE.md):
      - 按 Position 退出日期累计，不按逐笔 Trade
      - 起点: {首笔 exit_date, cum_pnl=0.0, cum_pnl_pct=0.0}
      - 后续逐笔累加
    """

    def test_equity_curve_exists_and_nonempty(self, client):
        """equity_curve 字段存在且至少含起点 + 1 个持仓退出点。"""
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        data = resp.json()
        assert "equity_curve" in data
        curve = data["equity_curve"]
        assert len(curve) >= 2  # 起点 + 至少 1 个 position

    def test_equity_curve_start_point_is_zero(self, client):
        """起点 cum_pnl 和 cum_pnl_pct 均为 0.0。"""
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        curve = resp.json()["equity_curve"]
        first = curve[0]
        assert first["cum_pnl"] == 0.0
        assert first["cum_pnl_pct"] == 0.0

    def test_equity_curve_cumulative_matches_total_pnl(self, client):
        """最后一个点的 cum_pnl 应等于全部有效持仓 PnL 之和。"""
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        data = resp.json()
        curve = data["equity_curve"]
        last = curve[-1]
        # Position 1: +490, Position 2: -706 → total = -216
        assert last["cum_pnl"] == data["total_pnl"]

    def test_equity_curve_dates_are_position_exit_dates(self, client):
        """曲线中的日期应来自持仓退出日期，按时间排序。"""
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        curve = resp.json()["equity_curve"]
        dates = [p["date"] for p in curve]
        # 至少包含两个退出日期: 2024-01-08 和 2024-02-05
        assert "2024-01-08" in dates
        assert "2024-02-05" in dates
        # 日期应按时间递增
        assert dates == sorted(dates)

    def test_equity_curve_cumulative_is_running_sum(self, client):
        """每个点的 cum_pnl 是到该点为止所有持仓 PnL 的累加。"""
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        curve = resp.json()["equity_curve"]
        # 跳过起点 (cum_pnl=0)，检查后续累加
        # Position 1 (000001) exit 01-08: pnl=+490
        # Position 2 (600001) exit 02-05: pnl=-706
        # 找到 01-08 和 02-05 对应的点
        pnl_by_date = {}
        for pt in curve:
            if pt["cum_pnl"] != 0.0 or pt is curve[0]:
                pnl_by_date[pt["date"]] = pt["cum_pnl"]
        # 01-08 的 cum_pnl 应为 490 (第一笔持仓退出)
        assert pnl_by_date.get("2024-01-08") == 490.0
        # 02-05 的 cum_pnl 应为 490 + (-706) = -216
        assert pnl_by_date.get("2024-02-05") == -216.0

    def test_equity_curve_empty_when_no_trades(self, client):
        """无交易时 equity_curve 应为空列表。"""
        resp = client.post(
            "/api/analysis/run",
            headers=self.headers,
            json={"date_start": "2023-01-01", "date_end": "2023-01-31"},
        )
        aid = resp.json()["analysis_id"]
        resp = client.get(f"/api/analysis/{aid}/stats", headers=self.headers)
        curve = resp.json()["equity_curve"]
        assert curve == []


class TestSymbolSummary(_BaseAnalysisTest):
    """V4.0: symbol_summary — 按个股汇总的盈亏统计。

    领域定义 (CLAUDE.md):
      - 仅统计 cost_known=True 的有效持仓 (valid_positions)
      - 字段: symbol, trade_count, win_count, win_rate, total_pnl,
              avg_holding_days, first_trade_date, last_trade_date
    """

    def test_symbol_summary_exists_and_nonempty(self, client):
        """symbol_summary 字段存在且包含每个个股一条记录。"""
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        data = resp.json()
        assert "symbol_summary" in data
        summary = data["symbol_summary"]
        assert len(summary) == 2  # 000001 + 600001

    def test_symbol_summary_contains_both_symbols(self, client):
        """两个股票代码都应出现在汇总中。"""
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        summary = resp.json()["symbol_summary"]
        symbols = {s["symbol"] for s in summary}
        assert "000001" in symbols
        assert "600001" in symbols

    def test_symbol_summary_winner_stats(self, client):
        """盈利个股 000001 的统计数据正确。

        Note: first_trade_date / last_trade_date 的语义待确认。
        字段名暗示首末成交日期，但当前实现返回持仓退出日期。
        """
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        summary = resp.json()["symbol_summary"]
        item = next(s for s in summary if s["symbol"] == "000001")
        assert item["trade_count"] == 1
        assert item["win_count"] == 1
        assert item["win_rate"] == 1.0
        assert item["total_pnl"] == 490.0
        assert item["avg_holding_days"] == 3.0
        # 000001: trades on 01-05 (buy) and 01-08 (sell)
        assert item["first_trade_date"] is not None
        assert item["last_trade_date"] is not None
        assert item["first_trade_date"] <= item["last_trade_date"]

    def test_symbol_summary_loser_stats(self, client):
        """亏损个股 600001 的统计数据正确。

        Note: first_trade_date / last_trade_date 的语义待确认。
        字段名暗示首末成交日期，但当前实现返回持仓退出日期。
        """
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
            headers=self.headers,
        )
        summary = resp.json()["symbol_summary"]
        item = next(s for s in summary if s["symbol"] == "600001")
        assert item["trade_count"] == 1
        assert item["win_count"] == 0
        assert item["win_rate"] == 0.0
        assert item["total_pnl"] == -706.0
        assert item["avg_holding_days"] == 4.0
        # 600001: trades on 02-01 (buy) and 02-05 (sell)
        assert item["first_trade_date"] is not None
        assert item["last_trade_date"] is not None
        assert item["first_trade_date"] <= item["last_trade_date"]

    def test_symbol_summary_empty_when_no_trades(self, client):
        """无交易时 symbol_summary 应为空列表。"""
        resp = client.post(
            "/api/analysis/run",
            headers=self.headers,
            json={"date_start": "2023-01-01", "date_end": "2023-01-31"},
        )
        aid = resp.json()["analysis_id"]
        resp = client.get(f"/api/analysis/{aid}/stats", headers=self.headers)
        summary = resp.json()["symbol_summary"]
        assert summary == []

    def test_symbol_summary_all_losing(self, client):
        """全亏损场景: 每个股票 win_count=0, win_rate=0.0。"""
        headers = get_auth_header(client, "sym_all_loss@test.com")
        raw_file_id = _import_csv(client, headers, ALL_LOSS_CSV)
        aid = run_analysis(client, headers, raw_file_id=raw_file_id)
        resp = client.get(f"/api/analysis/{aid}/stats", headers=headers)
        summary = resp.json()["symbol_summary"]
        assert len(summary) == 2
        for item in summary:
            assert item["win_count"] == 0
            assert item["win_rate"] == 0.0
            assert item["total_pnl"] < 0

    def test_symbol_summary_all_winning(self, client):
        """全盈利场景: 每个股票 win_count=1, win_rate=1.0。"""
        headers = get_auth_header(client, "sym_all_win@test.com")
        raw_file_id = _import_csv(client, headers, ALL_WIN_CSV)
        aid = run_analysis(client, headers, raw_file_id=raw_file_id)
        resp = client.get(f"/api/analysis/{aid}/stats", headers=headers)
        summary = resp.json()["symbol_summary"]
        assert len(summary) == 2
        for item in summary:
            assert item["win_count"] == 1
            assert item["win_rate"] == 1.0
            assert item["total_pnl"] > 0


# Required fields that the old incomplete snapshot (12 fields) was missing,
# causing `StatsResponse(**snapshot)` to raise ValidationError → 422.
_REQUIRED_SNAPSHOT_FIELDS = (
    "positions",
    "max_win",
    "max_loss",
    "consecutive_losses",
    "pnl_distribution",
    "equity_curve",
    "symbol_summary",
    "expectancy",
    "avg_mae",
    "avg_mfe",
    "total_return_pct",
    "max_drawdown_pct",
)


class TestSnapshotRoundTrip:
    """Regression: the get_stats slow path must cache a FIELD-COMPLETE snapshot.

    Root cause (fixed): when run_analysis's compute_all failed on the server
    (e.g. mootdx TCP errors), stats_snapshot stayed None. The first GET /stats
    then took the slow path, returned correct data, BUT saved a 12-field
    "summary" dict into stats_snapshot. The second GET /stats hit the fast path
    `StatsResponse(**snapshot)`, which raised ValidationError (missing
    positions/max_win/max_loss/consecutive_losses) → 422 → 分析面板 permanently
    showed "加载失败". This is the exact scenario the user hit: upload → view
    panel (OK) → generate AI report → return to panel (broken) → history →
    panel (still broken).

    These tests force the slow path by nulling the snapshot, then verify the
    snapshot written back is complete enough to round-trip through the fast
    path on the next request.
    """

    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.headers = get_auth_header(client)
        self.raw_file_id = import_trades(client, self.headers)
        self.analysis_id = run_analysis(
            client, self.headers, raw_file_id=self.raw_file_id
        )

    def _null_snapshot(self, db_session):
        """Simulate compute_all failing on the server: drop the precomputed snapshot."""
        analysis = (
            db_session.query(Analysis)
            .filter(Analysis.id == self.analysis_id)
            .first()
        )
        assert analysis is not None, "analysis not found in test db"
        analysis.stats_snapshot = None
        analysis.insight_snapshot = None
        analysis.whatif_snapshot = None
        db_session.commit()

    def test_slow_path_caches_field_complete_snapshot(self, client, db_session):
        """First GET after snapshot loss must return 200 AND persist a complete snapshot."""
        self._null_snapshot(db_session)

        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats", headers=self.headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # First call returns computed data with required fields present.
        assert len(data["positions"]) == 2
        assert data["max_win"] is not None
        assert data["max_loss"] is not None

        # The snapshot now stored must carry every required field.
        db_session.expire_all()
        analysis = (
            db_session.query(Analysis)
            .filter(Analysis.id == self.analysis_id)
            .first()
        )
        snapshot = analysis.stats_snapshot
        assert snapshot is not None, "slow path did not cache a snapshot"
        for field in _REQUIRED_SNAPSHOT_FIELDS:
            assert field in snapshot, (
                f"cached snapshot missing required field '{field}' "
                f"(this is the 422 bug: fast path StatsResponse(**snapshot) would raise)"
            )
        assert len(snapshot["positions"]) == 2

    def test_second_get_uses_fast_path_without_error(self, client, db_session):
        """The exact user scenario: view → return later → must NOT 422.

        Before the fix, the second request raised ValidationError because the
        slow path had cached a 12-field dict lacking `positions` etc.
        """
        self._null_snapshot(db_session)

        first = client.get(
            f"/api/analysis/{self.analysis_id}/stats", headers=self.headers
        )
        assert first.status_code == 200

        second = client.get(
            f"/api/analysis/{self.analysis_id}/stats", headers=self.headers
        )
        # Regression: this was 422 (ValidationError) before the fix.
        assert second.status_code == 200, (
            f"second GET /stats failed ({second.status_code}): {second.text}"
        )
        assert second.json()["positions"] == first.json()["positions"]
        assert second.json()["total_pnl"] == first.json()["total_pnl"]

    def test_stale_partial_snapshot_self_heals(self, client, db_session):
        """A truthy but INCOMPLETE legacy snapshot must self-heal, not 422.

        Distinct from snapshot=None (which skips the fast path entirely): a
        legacy 12-field partial dict is truthy, so the fast path runs
        ``StatsResponse(**snapshot)`` and hits ValidationError on the missing
        required fields (positions, max_win, consecutive_losses, ...). Without
        the self-heal the analysis 422s forever — the exact存量脏快照 scenario
        that the model_dump() fix does NOT repair (it only governs new writes).
        The fast path must catch the ValidationError, drop the stale snapshot,
        and fall through to the slow path, which recomputes AND overwrites a
        complete snapshot.
        """
        analysis = (
            db_session.query(Analysis)
            .filter(Analysis.id == self.analysis_id)
            .first()
        )
        # The legacy 12-field shape: truthy, but missing every required field
        # that has no default (positions, max_win, max_loss, consecutive_losses).
        analysis.stats_snapshot = {
            "total_trades": 4,
            "total_positions": 2,
            "win_count": 1,
            "win_rate": 0.5,
            "total_pnl": -216.0,
            "avg_holding_days": 3.5,
        }
        db_session.commit()

        # Before self-heal: fast path raises ValidationError → 422.
        # After self-heal: catches it, falls back to slow path → 200.
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats", headers=self.headers
        )
        assert resp.status_code == 200, (
            f"stale partial snapshot should self-heal, got {resp.status_code}: {resp.text}"
        )

        # The slow path must have overwritten the stale snapshot with a
        # complete one, so a subsequent fast-path request works cleanly.
        db_session.expire_all()
        analysis = (
            db_session.query(Analysis)
            .filter(Analysis.id == self.analysis_id)
            .first()
        )
        snapshot = analysis.stats_snapshot
        assert "positions" in snapshot, (
            "slow path did not overwrite the stale partial snapshot"
        )
        again = client.get(
            f"/api/analysis/{self.analysis_id}/stats", headers=self.headers
        )
        assert again.status_code == 200
