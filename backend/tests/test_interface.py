"""Interface/Contract Tests — HTTP parameter validation, response shapes, edge cases."""

import io
from unittest.mock import AsyncMock, patch

import pytest


# Password policy (CLAUDE.md): ≥8 chars + letter + digit. All test users share
# one valid password; weak passwords for the rejection test use <8 chars.
_TEST_PASSWORD = "pass1234"


def _qmt_csv():
    """Generate valid QMT-format CSV with proper UTF-8 encoding."""
    return "委托时间,证券代码,买卖方向,成交价格,成交数量\n2026-01-05 09:35:00,600519,买入,1500.00,100\n2026-01-10 14:20:00,600519,卖出,1520.00,100\n"


class TestAuthContracts:
    def test_register_response_shape(self, client):
        resp = client.post("/api/auth/register", json={"email": "ct@test.com", "password": "pass1234"})
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_register_short_password_rejected(self, client):
        resp = client.post("/api/auth/register", json={"email": "x@test.com", "password": "12345"})
        assert resp.status_code == 400

    def test_register_invalid_email_rejected(self, client):
        resp = client.post("/api/auth/register", json={"email": "notanemail", "password": "pass1234"})
        assert resp.status_code == 422

    def test_register_missing_fields(self, client):
        resp = client.post("/api/auth/register", json={"email": "x@test.com"})
        assert resp.status_code == 422

    def test_login_response_shape(self, client):
        client.post("/api/auth/register", json={"email": "lt@test.com", "password": "pass1234"})
        resp = client.post("/api/auth/login", json={"account": "lt@test.com", "password": "pass1234"})
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "access_token" in data
        assert "token_type" in data

    def test_login_invalid_credentials(self, client):
        resp = client.post("/api/auth/login", json={"account": "no@test.com", "password": "wrongpass1"})
        assert resp.status_code == 401

    def test_login_missing_password(self, client):
        resp = client.post("/api/auth/login", json={"email": "x@test.com"})
        assert resp.status_code == 422


class TestUploadContracts:
    def _auth(self, client):
        resp = client.post("/api/auth/register", json={"email": "up@test.com", "password": "pass1234"})
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    def test_upload_no_auth_rejected(self, client):
        csv_bytes = _qmt_csv().encode("utf-8")
        resp = client.post("/api/upload", files={"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")})
        assert resp.status_code == 403

    def test_upload_csv_detects_format(self, client):
        headers = self._auth(client)
        csv_bytes = _qmt_csv().encode("utf-8")
        resp = client.post("/api/upload", files={"file": ("trades.csv", io.BytesIO(csv_bytes), "text/csv")}, headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "raw_file_id" in data
        assert "detected_formats" in data
        assert isinstance(data["detected_formats"], list)

    def test_confirm_without_raw_file(self, client):
        headers = self._auth(client)
        resp = client.post("/api/upload/confirm", json={"raw_file_id": "nonexistent", "source_type": "smart"}, headers=headers)
        assert resp.status_code == 404

    def test_import_without_confirm(self, client):
        headers = self._auth(client)
        resp = client.post("/api/upload/import", json={"raw_file_id": "nonexistent"}, headers=headers)
        assert resp.status_code in (400, 404)

    def test_full_upload_flow(self, client):
        headers = self._auth(client)
        csv_bytes = _qmt_csv().encode("utf-8")
        files = {"file": ("qmt_trades.csv", io.BytesIO(csv_bytes), "text/csv")}

        resp = client.post("/api/upload", files=files, headers=headers)
        assert resp.status_code in (200, 201)
        upload_data = resp.json()
        raw_id = upload_data["raw_file_id"]

        resp = client.post("/api/upload/confirm", json={"raw_file_id": raw_id, "source_type": "smart"}, headers=headers)
        assert resp.status_code in (200, 201)
        confirm_data = resp.json()
        assert confirm_data["count"] == 2
        assert len(confirm_data["trades"]) == 2

        resp = client.post("/api/upload/import", json={"raw_file_id": raw_id}, headers=headers)
        assert resp.status_code in (200, 201)
        import_data = resp.json()
        assert import_data["imported_count"] == 2


class TestAnalysisContracts:
    def _auth_and_import(self, client):
        resp = client.post("/api/auth/register", json={"email": "an@test.com", "password": "pass1234"})
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        csv_bytes = _qmt_csv().encode("utf-8")
        files = {"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")}
        up = client.post("/api/upload", files=files, headers=headers)
        raw_id = up.json()["raw_file_id"]
        client.post("/api/upload/confirm", json={"raw_file_id": raw_id, "source_type": "smart"}, headers=headers)
        client.post("/api/upload/import", json={"raw_file_id": raw_id}, headers=headers)
        return headers

    def test_run_analysis(self, client):
        headers = self._auth_and_import(client)
        resp = client.post("/api/analysis/run", json={"date_start": "2026-01-01", "date_end": "2026-12-31"}, headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "analysis_id" in data

    def test_stats_response_shape(self, client):
        headers = self._auth_and_import(client)
        run = client.post("/api/analysis/run", json={"date_start": "2026-01-01", "date_end": "2026-12-31"}, headers=headers)
        aid = run.json()["analysis_id"]
        resp = client.get(f"/api/analysis/{aid}/stats", headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "total_trades" in data
        assert "win_rate" in data
        assert "total_pnl" in data
        assert "positions" in data

    def test_insight_response_shape(self, client):
        headers = self._auth_and_import(client)
        run = client.post("/api/analysis/run", json={"date_start": "2026-01-01", "date_end": "2026-12-31"}, headers=headers)
        aid = run.json()["analysis_id"]
        resp = client.get(f"/api/analysis/{aid}/insight", headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "patterns" in data
        assert "best_pattern" in data
        assert "worst_pattern" in data

    def test_whatif_response_shape(self, client):
        headers = self._auth_and_import(client)
        run = client.post("/api/analysis/run", json={"date_start": "2026-01-01", "date_end": "2026-12-31"}, headers=headers)
        aid = run.json()["analysis_id"]
        resp = client.get(f"/api/analysis/{aid}/whatif", headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "items" in data
        for item in data["items"]:
            assert "removed_pattern" in item
            assert "original_return" in item
            assert "what_if_return" in item
            assert "delta" in item
            assert "contribution_pct" in item

    def test_analysis_404_bad_id(self, client):
        headers = self._auth_and_import(client)
        resp = client.get("/api/analysis/notexist/stats", headers=headers)
        assert resp.status_code == 404

    def test_analysis_cross_user_isolation(self, client):
        headers = self._auth_and_import(client)
        run = client.post("/api/analysis/run", json={"date_start": "2026-01-01", "date_end": "2026-12-31"}, headers=headers)
        aid = run.json()["analysis_id"]
        client.post("/api/auth/register", json={"email": "other@test.com", "password": "pass1234"})
        other_login = client.post("/api/auth/login", json={"account": "other@test.com", "password": "pass1234"})
        other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
        resp = client.get(f"/api/analysis/{aid}/stats", headers=other_headers)
        assert resp.status_code == 404


class TestReportContracts:
    def _setup(self, client):
        resp = client.post("/api/auth/register", json={"email": "rp@test.com", "password": "pass1234"})
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        csv_bytes = _qmt_csv().encode("utf-8")
        files = {"file": ("t.csv", io.BytesIO(csv_bytes), "text/csv")}
        up = client.post("/api/upload", files=files, headers=headers)
        raw_id = up.json()["raw_file_id"]
        client.post("/api/upload/confirm", json={"raw_file_id": raw_id, "source_type": "smart"}, headers=headers)
        client.post("/api/upload/import", json={"raw_file_id": raw_id}, headers=headers)
        run = client.post("/api/analysis/run", json={"date_start": "2026-01-01", "date_end": "2026-12-31"}, headers=headers)
        return headers, run.json()["analysis_id"]

    @patch("app.api.report.get_llm")
    def test_generate_report(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value="## 核心诊断\n胜率42%，总收益12%")
        mock_get_llm.return_value = mock_provider
        headers, aid = self._setup(client)
        resp = client.post("/api/report/generate", json={"analysis_id": aid}, headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "report_id" in data
        assert data["status"] == "generated"

    @patch("app.api.report.get_llm")
    def test_get_report_by_id(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value="## 核心诊断\n测试报告")
        mock_get_llm.return_value = mock_provider
        headers, aid = self._setup(client)
        gen = client.post("/api/report/generate", json={"analysis_id": aid}, headers=headers)
        rid = gen.json()["report_id"]
        resp = client.get(f"/api/report/{rid}", headers=headers)
        assert resp.status_code in (200, 201)
        assert resp.json()["id"] == rid

    @patch("app.api.report.get_llm")
    def test_list_reports(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value="## 核心诊断\n测试")
        mock_get_llm.return_value = mock_provider
        headers, aid = self._setup(client)
        client.post("/api/report/generate", json={"analysis_id": aid}, headers=headers)
        resp = client.get("/api/reports", headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "reports" in data
        assert data["total"] >= 1

    @patch("app.api.report.get_llm")
    def test_report_cross_user_isolation(self, mock_get_llm, client):
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value="## 核心诊断\n测试")
        mock_get_llm.return_value = mock_provider
        headers, aid = self._setup(client)
        gen = client.post("/api/report/generate", json={"analysis_id": aid}, headers=headers)
        rid = gen.json()["report_id"]
        client.post("/api/auth/register", json={"email": "oth2@test.com", "password": "pass1234"})
        other = client.post("/api/auth/login", json={"account": "oth2@test.com", "password": "pass1234"})
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        resp = client.get(f"/api/report/{rid}", headers=other_headers)
        assert resp.status_code == 404

    def test_generate_report_no_auth(self, client):
        resp = client.post("/api/report/generate", json={"analysis_id": "x"})
        assert resp.status_code == 403

    def test_list_reports_empty(self, client):
        resp = client.post("/api/auth/register", json={"email": "noreports@test.com", "password": "pass1234"})
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
        resp = client.get("/api/reports", headers=headers)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["reports"] == []
        assert data["total"] == 0
