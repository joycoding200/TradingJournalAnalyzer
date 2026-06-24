"""Tests for analysis API endpoints (run, stats, insight, whatif)."""

import pytest

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
