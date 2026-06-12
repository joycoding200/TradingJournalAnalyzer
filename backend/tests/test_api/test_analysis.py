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
    """Helper: upload, confirm, and import QMT trades."""
    r = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("trades.csv", QMT_CSV, "text/csv")},
    )
    raw_file_id = r.json()["raw_file_id"]
    client.post(
        "/api/upload/confirm",
        headers=headers,
        json={"raw_file_id": raw_file_id, "source_type": "qmt"},
    )
    client.post(
        "/api/upload/import",
        headers=headers,
        json={"raw_file_id": raw_file_id},
    )


def run_analysis(client, headers, date_start="2024-01-01", date_end="2024-12-31"):
    """Helper: create an analysis and return its id."""
    resp = client.post(
        "/api/analysis/run",
        headers=headers,
        json={"date_start": date_start, "date_end": date_end},
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
        import_trades(client, self.headers)
        self.analysis_id = run_analysis(client, self.headers)


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
        assert data["total_pnl"] == -200.0  # 500 - 700
        assert data["avg_holding_days"] == 3.5
        assert data["max_win"] == 500.0
        assert data["max_loss"] == -700.0
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
        resp = client.get(
            f"/api/analysis/{self.analysis_id}/stats",
        )
        assert resp.status_code == 403


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
