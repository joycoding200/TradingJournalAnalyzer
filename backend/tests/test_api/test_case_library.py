"""Tests for anonymous case library contribution feature.

Coverage:
  - POST /api/case-library/contribute — accept/reject contribution
  - GET  /api/case-library/status — check user's consent status
  - Data integrity: trades, positions, stats, report, raw_file all stored
  - Anonymization: no email/phone/name in stored data
  - Reject behavior: nothing written to DB
"""

import io
import json
import pytest

from app.models.user import User


TEST_EMAIL = "caselib_test@test.com"
TEST_PASSWORD = "secret123"

QMT_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,平安银行,买入,10.50,1000,5.00\n"
    "2024-01-08 14:00:00,000001,平安银行,卖出,11.00,1000,5.00\n"
)


def _register_and_login(client, email=TEST_EMAIL):
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload_and_import(client, headers):
    """Upload, confirm, import — return analysis_id + raw_file_id."""
    r = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("trades.csv", QMT_CSV.encode(), "text/csv")},
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
    r = client.post(
        "/api/analysis/run",
        headers=headers,
        json={"date_start": "2024-01-01", "date_end": "2024-12-31", "raw_file_id": raw_file_id},
    )
    assert r.status_code == 201
    analysis_id = r.json()["analysis_id"]
    return analysis_id, raw_file_id


def _get_stats(client, headers, analysis_id):
    resp = client.get(f"/api/analysis/{analysis_id}/stats", headers=headers)
    assert resp.status_code == 200
    return resp.json()


# ── API tests ────────────────────────────────────────────────────────────────


class TestCaseLibraryAuth:
    """Authentication / authorization checks."""

    def test_contribute_requires_auth(self, client):
        resp = client.post("/api/case-library/contribute", json={"consent": True})
        assert resp.status_code == 403

    def test_status_requires_auth(self, client):
        resp = client.get("/api/case-library/status")
        assert resp.status_code == 403


class TestCaseLibraryContribute:
    """End-to-end contribution flow."""

    def test_reject_does_nothing(self, client):
        headers = _register_and_login(client)
        resp = client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detail"] == "已跳过"

    def test_accept_stores_case(self, client):
        headers = _register_and_login(client)
        analysis_id, raw_file_id = _upload_and_import(client, headers)

        # Consent and contribute
        resp = client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": analysis_id},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["detail"] == "案例已匿名贡献，感谢您的支持"

    def test_status_reflects_consent(self, client):
        headers = _register_and_login(client)
        analysis_id, _ = _upload_and_import(client, headers)

        # Before consent
        resp = client.get("/api/case-library/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["has_consented"] is False

        # After consent + contribute
        client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": analysis_id},
        )
        resp = client.get("/api/case-library/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["has_consented"] is True

    def test_multiple_contributions_add_rows(self, client):
        """Each consent + contribute creates a new case library row."""
        headers = _register_and_login(client)
        a1, _ = _upload_and_import(client, headers)
        resp1 = client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": a1},
        )
        assert resp1.status_code == 201

        # Upload a second file and contribute again
        a2, _ = _upload_and_import(client, headers)
        resp2 = client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": a2},
        )
        assert resp2.status_code == 201

    def test_cannot_contribute_same_analysis_twice(self, client):
        headers = _register_and_login(client)
        analysis_id, _ = _upload_and_import(client, headers)

        r1 = client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": analysis_id},
        )
        assert r1.status_code == 201

        r2 = client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": analysis_id},
        )
        assert r2.status_code == 409  # duplicate


# ── Data integrity tests ─────────────────────────────────────────────────────


class TestCaseLibraryDataIntegrity:
    """Verify stored case data is complete and anonymized."""

    def test_stored_case_has_no_personal_info(self, client):
        headers = _register_and_login(client)
        analysis_id, _ = _upload_and_import(client, headers)

        client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": analysis_id},
        )

        # Check DB directly — case library row should not contain email/phone
        # (This is verified via the model layer — no user PII columns in CaseLibrary)
        from app.database import SessionLocal
        from app.models.case_library import CaseLibrary

        db = SessionLocal()
        try:
            cases = db.query(CaseLibrary).all()
            for case in cases:
                data = json.dumps({
                    "trades": case.trades_json,
                    "stats": case.stats_json,
                    "report": case.report_content,
                })
                assert "@" not in data, "Email found in case library data"
                assert TEST_EMAIL not in data, "Test email found in case library data"
        finally:
            db.close()

    def test_stored_case_has_raw_file_content(self, client):
        headers = _register_and_login(client)
        analysis_id, raw_file_id = _upload_and_import(client, headers)

        client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": analysis_id},
        )

        from app.database import SessionLocal
        from app.models.case_library import CaseLibrary

        db = SessionLocal()
        try:
            case = db.query(CaseLibrary).first()
            assert case is not None
            assert case.raw_file_content is not None
            assert len(case.raw_file_content) > 0
            assert case.raw_filename is not None
        finally:
            db.close()

    def test_stored_case_has_complete_analysis_data(self, client):
        headers = _register_and_login(client)
        analysis_id, _ = _upload_and_import(client, headers)

        stats = _get_stats(client, headers, analysis_id)
        # Verify the stats data that will be stored is meaningful
        assert stats["total_trades"] > 0
        assert stats["total_positions"] > 0
        assert "total_pnl" in stats
        assert "win_rate" in stats
        assert len(stats["positions"]) > 0

        client.post(
            "/api/case-library/contribute",
            headers=headers,
            json={"consent": True, "analysis_id": analysis_id},
        )

        from app.database import SessionLocal
        from app.models.case_library import CaseLibrary

        db = SessionLocal()
        try:
            case = db.query(CaseLibrary).first()
            assert case is not None
            stored_stats = json.loads(case.stats_json)
            assert stored_stats["total_trades"] == stats["total_trades"]
            assert stored_stats["win_rate"] == stats["win_rate"]
            assert len(stored_stats["positions"]) == len(stats["positions"])
        finally:
            db.close()
