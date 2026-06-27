"""Tests for the data lifecycle endpoint: DELETE /api/upload/trades.

User path: after uploading statements, running analyses and generating reports,
the user can wipe ALL their data in one irreversible call. This is the only
endpoint that deletes reports/analyses/trades/raw-files in FK-safe order, and it
had zero test coverage.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.analysis import Analysis, AnalysisFile
from app.models.consent_log import ConsentLog
from app.models.raw_file import RawFile
from app.models.report import Report
from app.models.trade import Trade

QMT_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,平安银行,买入,10.50,1000,5.00\n"
    "2024-01-10 14:00:00,000001,平安银行,卖出,11.00,1000,5.00\n"
    "2024-02-01 09:30:00,600001,包钢股份,买入,5.00,2000,3.00\n"
    "2024-02-05 14:00:00,600001,包钢股份,卖出,4.50,2000,3.00"
)

MOCK_REPORT = "## 核心结论\n测试报告\n\n## 改善建议\n- 严格控制亏损"

TEST_PASSWORD = "secret123"


def _register(client, email):
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _full_setup(client, headers):
    """Upload → confirm → import → run analysis → generate report."""
    r = client.post(
        "/api/upload", headers=headers, files={"file": ("t.csv", QMT_CSV, "text/csv")}
    )
    raw_file_id = r.json()["raw_file_id"]
    client.post(
        "/api/upload/confirm",
        headers=headers,
        json={"raw_file_id": raw_file_id, "source_type": "smart"},
    )
    client.post(
        "/api/upload/import", headers=headers, json={"raw_file_id": raw_file_id}
    )
    aid = client.post(
        "/api/analysis/run",
        headers=headers,
        json={
            "date_start": "2024-01-01",
            "date_end": "2024-12-31",
            "raw_file_id": raw_file_id,
        },
    ).json()["analysis_id"]

    with patch("app.api.report.get_llm") as mock_get_llm:
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=MOCK_REPORT)
        mock_get_llm.return_value = mock_provider
        rid = client.post(
            "/api/report/generate",
            headers=headers,
            json={"analysis_id": aid},
        ).json()["report_id"]
    return raw_file_id, aid, rid


@pytest.fixture
def user_with_data(client, db_session):
    headers = _register(client, "lifecycle@test.com")
    raw_file_id, analysis_id, report_id = _full_setup(client, headers)
    # API requests commit through their own sessions; force this session to
    # start a fresh transaction so it sees the committed rows.
    db_session.rollback()
    return headers, raw_file_id, analysis_id, report_id


def _refresh(db_session):
    """Drop this session's transaction snapshot so it sees committed rows."""
    db_session.rollback()


def _user_id_from_headers(headers):
    """Decode the user id from the bearer token (for DB assertions)."""
    from jose import jwt

    token = headers["Authorization"].split(" ", 1)[1]
    # Read the `sub` claim without verifying the signature — the token was
    # just minted by the app, we only need its user id for DB scoping.
    return jwt.get_unverified_claims(token)["sub"]


class TestClearTrades:
    def test_clear_trades_requires_auth(self, client):
        assert client.delete("/api/upload/trades").status_code == 403

    def test_clear_trades_wipes_all_data(self, client, db_session, user_with_data):
        """All user data tables empty after wipe, in FK-safe order."""
        headers, raw_file_id, analysis_id, report_id = user_with_data
        user_id = _user_id_from_headers(headers)

        # Precondition: data exists
        assert db_session.query(Report).filter_by(user_id=user_id).count() == 1
        assert db_session.query(Analysis).filter_by(user_id=user_id).count() == 1
        assert db_session.query(Trade).filter_by(user_id=user_id).count() > 0
        assert db_session.query(RawFile).filter_by(user_id=user_id).count() == 1

        resp = client.delete("/api/upload/trades", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["detail"] == "所有交易数据已永久删除"

        # FK-safe deletion left nothing behind
        _refresh(db_session)
        assert db_session.query(Report).filter_by(user_id=user_id).count() == 0
        assert db_session.query(AnalysisFile).count() == 0  # join table cleared
        assert db_session.query(Analysis).filter_by(user_id=user_id).count() == 0
        assert db_session.query(Trade).filter_by(user_id=user_id).count() == 0
        # consent_log is NOT cleared: it is an immutable compliance audit trail.
        # (No rows exist for this fixture, so count stays 0 — the behavioral
        # retention is asserted in test_clear_trades_preserves_consent_log.)
        assert db_session.query(RawFile).filter_by(user_id=user_id).count() == 0

        # The user's upload directory is removed
        from app.api.upload import UPLOAD_ROOT

        assert not (UPLOAD_ROOT / user_id).exists()

    def test_clear_trades_preserves_consent_log(self, client, db_session):
        """consent_log must survive clear_trades — it is immutable compliance
        evidence. A contributed case stays in the library; the consent that
        authorized it cannot be erased by clearing the user's own trading data.
        Decline records are likewise retained as evidence of the choice.

        Regression: clear_trades used to physically delete ConsentLog rows,
        destroying the audit trail it was designed to keep.
        """
        headers = _register(client, "consent_keep@test.com")
        raw_file_id, analysis_id, _ = _full_setup(client, headers)
        user_id = _user_id_from_headers(headers)

        # Seed one agree + one decline record against this user's analysis.
        db_session.add(
            ConsentLog(user_id=user_id, analysis_id=analysis_id, consented=True)
        )
        db_session.add(
            ConsentLog(user_id=user_id, analysis_id=analysis_id, consented=False)
        )
        db_session.commit()

        resp = client.delete("/api/upload/trades", headers=headers)
        assert resp.status_code == 200

        _refresh(db_session)
        # Both consent rows survive the wipe.
        rows = (
            db_session.query(ConsentLog)
            .filter_by(user_id=user_id)
            .order_by(ConsentLog.created_at)
            .all()
        )
        assert len(rows) == 2, (
            "consent_log must be preserved across clear_trades (audit trail)"
        )
        assert {r.consented for r in rows} == {True, False}

    def test_clear_trades_isolates_other_users(self, client, db_session):
        """Deleting A's data must not touch B's data."""
        a_headers = _register(client, "keepA@test.com")
        a_raw, a_aid, a_rid = _full_setup(client, a_headers)

        b_headers = _register(client, "wipeB@test.com")
        _full_setup(client, b_headers)

        # B wipes their data
        resp = client.delete("/api/upload/trades", headers=b_headers)
        assert resp.status_code == 200

        # A's data is untouched
        a_uid = _user_id_from_headers(a_headers)
        _refresh(db_session)
        assert db_session.query(Analysis).filter_by(id=a_aid).count() == 1
        assert db_session.query(RawFile).filter_by(id=a_raw).count() == 1
        assert db_session.query(Report).filter_by(id=a_rid).count() == 1

    def test_clear_trades_idempotent(self, client):
        """Wiping an already-empty account is a no-op success."""
        headers = _register(client, "empty@test.com")
        assert client.delete("/api/upload/trades", headers=headers).status_code == 200
        # Second wipe on empty account
        assert client.delete("/api/upload/trades", headers=headers).status_code == 200
