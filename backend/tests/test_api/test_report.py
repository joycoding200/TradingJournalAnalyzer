"""Tests for report API endpoints (generate, get, list)."""

from unittest.mock import AsyncMock, patch

import pytest

QMT_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,平安银行,买入,10.50,1000,5.00\n"
    "2024-01-10 14:00:00,000001,平安银行,卖出,11.00,1000,5.00\n"
    "2024-02-01 09:30:00,600001,包钢股份,买入,5.00,2000,3.00\n"
    "2024-02-05 14:00:00,600001,包钢股份,卖出,4.50,2000,3.00"
)

MOCK_REPORT = """## 核心结论
你的交易行为整体亏损，需重点关注亏损行为。

## 优势清单
- 完成4笔交易，持仓周期合理，以波段交易为主

## 风险警示
- 亏损交易占比过高，胜率：50%

## 改善建议
- 严格控制单笔亏损，设置止损位"""

TEST_EMAIL = "report_api_test@test.com"
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


def run_analysis(client, headers, raw_file_id=None):
    body = {"date_start": "2024-01-01", "date_end": "2024-12-31"}
    if raw_file_id:
        body["raw_file_id"] = raw_file_id
    resp = client.post(
        "/api/analysis/run",
        headers=headers,
        json=body,
    )
    return resp.json()["analysis_id"]


class _BaseReportTest:
    """Base class that sets up a user with trades and analysis."""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.headers = get_auth_header(client)
        raw_file_id = import_trades(client, self.headers)
        self.analysis_id = run_analysis(client, self.headers, raw_file_id)


class TestReportGenerate(_BaseReportTest):
    """Test report generation endpoint."""

    def test_generate_requires_auth(self, client):
        client.cookies.clear()
        resp = client.post(
            "/api/report/generate",
            json={"analysis_id": "some-id"},
        )
        assert resp.status_code == 403

    def test_generate_404_for_nonexistent_analysis(self, client):
        resp = client.post(
            "/api/report/generate",
            headers=self.headers,
            json={"analysis_id": "nonexistent"},
        )
        assert resp.status_code == 404

    @patch("app.api.report.get_llm")
    def test_generate_creates_report(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
        mock_get_llm.return_value = mock_provider

        resp = client.post(
            "/api/report/generate",
            headers=self.headers,
            json={"analysis_id": self.analysis_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "report_id" in data
        assert data["status"] == "generated"

    @patch("app.api.report.get_llm")
    def test_generated_report_content_stored(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
        mock_get_llm.return_value = mock_provider

        # Generate
        gen_resp = client.post(
            "/api/report/generate",
            headers=self.headers,
            json={"analysis_id": self.analysis_id},
        )
        report_id = gen_resp.json()["report_id"]

        # Fetch
        resp = client.get(
            f"/api/report/{report_id}",
            headers=self.headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == report_id
        assert "analysis_input" in data
        assert data["ai_provider"] != ""
        assert data["validation_passed"] is True
        assert "report_content" in data
        assert len(data["report_content"]) > 0
        assert "核心结论" in data["report_content"]


class TestReportGet(_BaseReportTest):
    """Test fetching individual reports."""

    def test_get_requires_auth(self, client):
        client.cookies.clear()
        resp = client.get("/api/report/some-id")
        assert resp.status_code == 403

    def test_get_404_for_nonexistent(self, client):
        resp = client.get("/api/report/nonexistent", headers=self.headers)
        assert resp.status_code == 404

    @patch("app.api.report.get_llm")
    def test_get_own_report_succeeds(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
        mock_get_llm.return_value = mock_provider

        # Generate
        gen_resp = client.post(
            "/api/report/generate",
            headers=self.headers,
            json={"analysis_id": self.analysis_id},
        )
        report_id = gen_resp.json()["report_id"]

        # Fetch
        resp = client.get(
            f"/api/report/{report_id}",
            headers=self.headers,
        )
        assert resp.status_code == 200

    @patch("app.api.report.get_llm")
    def test_cannot_access_other_users_report(self, mock_get_llm, client):
        """User B should not see User A's report (gets 404)."""
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
        mock_get_llm.return_value = mock_provider

        # User A: generate a report (using the setup fixture's user)
        gen_resp = client.post(
            "/api/report/generate",
            headers=self.headers,
            json={"analysis_id": self.analysis_id},
        )
        report_id = gen_resp.json()["report_id"]

        # User B: try to access User A's report
        headers_b = get_auth_header(client, "report_user_b@test.com")
        resp = client.get(
            f"/api/report/{report_id}",
            headers=headers_b,
        )
        assert resp.status_code == 404


class TestReportsList:
    """Test listing user's reports."""

    def test_list_reports_requires_auth(self, client):
        resp = client.get("/api/reports")
        assert resp.status_code == 403

    def test_list_reports_empty(self, client):
        headers = get_auth_header(client, "report_list_empty@test.com")
        resp = client.get("/api/reports", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["reports"] == []

    @patch("app.api.report.get_llm")
    def test_list_reports_after_generation(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
        mock_get_llm.return_value = mock_provider

        headers = get_auth_header(client, "report_list_gen@test.com")
        raw_file_id = import_trades(client, headers)
        analysis_id = run_analysis(client, headers, raw_file_id)

        # Generate a report
        client.post(
            "/api/report/generate",
            headers=headers,
            json={"analysis_id": analysis_id},
        )

        # List
        resp = client.get("/api/reports", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["reports"]) == 1


class TestReportInsightConsistency:
    """The AI report must reason over the SAME insight data the /insight panel
    shows. Previously report.py used InsightEngine.analyze (single primary-pattern
    bucketing) while the panel used compute_insight/analyze_by_category
    (multi-bucket, log-weighted, count>=5 filter), so the AI could cite a
    "best pattern" the panel excluded. These tests lock the unified data source.
    """

    def test_report_insight_matches_insight_endpoint(self, client):
        headers = get_auth_header(client, "insight_consistency@test.com")
        raw_file_id = import_trades(client, headers)
        analysis_id = run_analysis(client, headers, raw_file_id)

        with patch("app.api.report.get_llm") as mock_get_llm:
            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
            mock_get_llm.return_value = mock_provider
            gen = client.post(
                "/api/report/generate",
                headers=headers,
                json={"analysis_id": analysis_id},
            )
            assert gen.status_code == 201, gen.text
            report_id = gen.json()["report_id"]

        # The report's stored analysis_input.patterns must match the /insight
        # endpoint's patterns (same source: compute_insight).
        report = client.get(f"/api/report/{report_id}", headers=headers).json()
        report_patterns = {
            p["pattern_name"]: p for p in report["analysis_input"]["patterns"]
        }

        insight = client.get(
            f"/api/analysis/{analysis_id}/insight", headers=headers
        ).json()
        # /insight returns patterns flattened across all dimensions
        insight_patterns = {p["pattern_name"]: p for p in insight["patterns"]}

        # Every pattern the AI report sees must exist in the insight panel
        assert set(report_patterns) == set(insight_patterns), (
            f"report patterns != insight patterns: "
            f"report_only={set(report_patterns) - set(insight_patterns)} "
            f"insight_only={set(insight_patterns) - set(report_patterns)}"
        )
        # And their counts / total_pnl must agree (same computation)
        for name, rp in report_patterns.items():
            ip = insight_patterns[name]
            assert rp["count"] == ip["count"], (
                f"pattern '{name}' count drift: report={rp['count']} "
                f"insight={ip['count']}"
            )
            assert rp["total_pnl"] == ip["total_pnl"], (
                f"pattern '{name}' total_pnl drift: report={rp['total_pnl']} "
                f"insight={ip['total_pnl']}"
            )

    def test_report_uses_compute_insight_not_analyze(self, client, monkeypatch):
        """The report pipeline must draw insight patterns from the SAME source
        the /insight panel uses — never the divergent InsightEngine.analyze.

        With a snapshot (the normal case: run_analysis precomputes it), the
        report reads analysis.insight_snapshot directly, so it does NOT call
        compute_insight and must not call InsightEngine.analyze either. When no
        snapshot exists (legacy analysis), it falls back to compute_insight.
        """
        from app.engine import compute as compute_mod
        from app.engine import insight as insight_mod

        headers = get_auth_header(client, "compute_insight@test.com")
        raw_file_id = import_trades(client, headers)
        analysis_id = run_analysis(client, headers, raw_file_id)

        compute_calls = {"compute_insight": 0, "analyze": 0}
        orig_compute_insight = compute_mod.compute_insight
        orig_analyze = insight_mod.InsightEngine.analyze

        def spy_compute_insight(*args, **kwargs):
            compute_calls["compute_insight"] += 1
            return orig_compute_insight(*args, **kwargs)

        def spy_analyze(*args, **kwargs):
            compute_calls["analyze"] += 1
            return orig_analyze(*args, **kwargs)

        monkeypatch.setattr(compute_mod, "compute_insight", spy_compute_insight)
        monkeypatch.setattr(insight_mod.InsightEngine, "analyze", spy_analyze)

        with patch("app.api.report.get_llm") as mock_get_llm:
            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
            mock_get_llm.return_value = mock_provider
            gen = client.post(
                "/api/report/generate",
                headers=headers,
                json={"analysis_id": analysis_id},
            )
            assert gen.status_code == 201, gen.text

        # run_analysis precomputes insight_snapshot, so the report reads it
        # directly and does NOT recompute. Either way the divergent analyze
        # path must never run.
        assert compute_calls["analyze"] == 0, (
            "report generation must NOT call the divergent InsightEngine.analyze"
        )

    def test_report_recomputes_insight_when_no_snapshot(self, client, db_session, monkeypatch):
        """Legacy analyses without insight_snapshot must fall back to the shared
        compute_insight engine (still the unified source, not InsightEngine.analyze)."""
        from app.engine import compute as compute_mod
        from app.models.analysis import Analysis

        headers = get_auth_header(client, "compute_insight_nosnap@test.com")
        raw_file_id = import_trades(client, headers)
        analysis_id = run_analysis(client, headers, raw_file_id)

        # Drop the snapshot to force the slow path.
        db_session.rollback()
        analysis = db_session.query(Analysis).filter_by(id=analysis_id).first()
        analysis.insight_snapshot = None
        db_session.commit()

        compute_calls = {"compute_insight": 0}
        orig_compute_insight = compute_mod.compute_insight

        def spy_compute_insight(*args, **kwargs):
            compute_calls["compute_insight"] += 1
            return orig_compute_insight(*args, **kwargs)

        monkeypatch.setattr(compute_mod, "compute_insight", spy_compute_insight)

        with patch("app.api.report.get_llm") as mock_get_llm:
            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
            mock_get_llm.return_value = mock_provider
            gen = client.post(
                "/api/report/generate",
                headers=headers,
                json={"analysis_id": analysis_id},
            )
            assert gen.status_code == 201, gen.text

        assert compute_calls["compute_insight"] >= 1, (
            "report generation with no snapshot must fall back to compute_insight"
        )
