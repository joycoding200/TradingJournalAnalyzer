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


def run_analysis(client, headers):
    resp = client.post(
        "/api/analysis/run",
        headers=headers,
        json={"date_start": "2024-01-01", "date_end": "2024-12-31"},
    )
    return resp.json()["analysis_id"]


class _BaseReportTest:
    """Base class that sets up a user with trades and analysis."""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.headers = get_auth_header(client)
        import_trades(client, self.headers)
        self.analysis_id = run_analysis(client, self.headers)


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
        import_trades(client, headers)
        analysis_id = run_analysis(client, headers)

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
