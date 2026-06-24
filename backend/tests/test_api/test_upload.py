"""Tests for upload API endpoints (upload / confirm / import)."""

QMT_CSV = (
    "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
    "2024-01-05 09:30:00,000001,平安银行,买入,10.50,1000,5.00\n"
    "2024-01-10 14:00:00,000001,平安银行,卖出,11.00,1000,5.00\n"
    "2024-02-01 09:30:00,600001,包钢股份,买入,5.00,2000,3.00\n"
    "2024-02-05 14:00:00,600001,包钢股份,卖出,4.50,2000,3.00"
)


def get_auth_header(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "upload_test@test.com", "password": "Test1234"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestUploadFlow:
    """Test the 3-step upload flow."""

    def test_upload_file_detects_smart_format(self, client):
        headers = get_auth_header(client)
        resp = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("test.csv", QMT_CSV, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "raw_file_id" in data
        assert len(data["detected_formats"]) > 0
        # SmartParser should be among detected formats
        formats = {f["source_type"] for f in data["detected_formats"]}
        assert "smart" in formats

    def test_confirm_format_returns_trade_preview(self, client):
        headers = get_auth_header(client)
        # Upload first
        upload_resp = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("trades.csv", QMT_CSV, "text/csv")},
        )
        raw_file_id = upload_resp.json()["raw_file_id"]

        # Confirm
        resp = client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": raw_file_id, "source_type": "smart"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 4
        assert len(data["trades"]) == 4

        first = data["trades"][0]
        assert first["symbol"] == "000001"
        assert first["side"] == "BUY"
        assert first["quantity"] == 1000
        assert first["price"] == 10.5

    def test_import_saves_trades_to_db(self, client):
        headers = get_auth_header(client)
        upload_resp = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("trades.csv", QMT_CSV, "text/csv")},
        )
        raw_file_id = upload_resp.json()["raw_file_id"]

        # Confirm
        client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": raw_file_id, "source_type": "smart"},
        )

        # Import
        resp = client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": raw_file_id},
        )
        assert resp.status_code == 200
        assert resp.json()["imported_count"] == 4

    def test_full_upload_flow_integration(self, client):
        """Run all three steps sequentially."""
        headers = get_auth_header(client)

        # 1. Upload
        r1 = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("flow.csv", QMT_CSV, "text/csv")},
        )
        assert r1.status_code == 200
        raw_file_id = r1.json()["raw_file_id"]
        assert r1.json()["detected_formats"]

        # 2. Confirm
        r2 = client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": raw_file_id, "source_type": "smart"},
        )
        assert r2.status_code == 200
        assert r2.json()["count"] == 4

        # 3. Import
        r3 = client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": raw_file_id},
        )
        assert r3.status_code == 200
        assert r3.json()["imported_count"] == 4


class TestUploadErrors:
    """Test error cases for upload endpoints."""

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/api/upload",
            files={"file": ("test.csv", QMT_CSV, "text/csv")},
        )
        assert resp.status_code == 403

    def test_confirm_unknown_source_type(self, client):
        headers = get_auth_header(client)
        resp = client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": "nonexistent", "source_type": "unknown_format"},
        )
        assert resp.status_code == 404  # raw file not found first

    def test_confirm_invalid_source_type(self, client):
        headers = get_auth_header(client)
        # Upload first
        r = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("t.csv", QMT_CSV, "text/csv")},
        )
        raw_file_id = r.json()["raw_file_id"]

        resp = client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": raw_file_id, "source_type": "nonexistent_parser"},
        )
        assert resp.status_code == 400

    def test_import_before_confirm(self, client):
        headers = get_auth_header(client)
        r = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("t.csv", QMT_CSV, "text/csv")},
        )
        raw_file_id = r.json()["raw_file_id"]

        # Import without confirming
        resp = client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": raw_file_id},
        )
        assert resp.status_code == 400
        assert "Confirm" in resp.json()["detail"]

    def test_import_nonexistent_file(self, client):
        headers = get_auth_header(client)
        resp = client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": "no-such-id"},
        )
        assert resp.status_code == 404
