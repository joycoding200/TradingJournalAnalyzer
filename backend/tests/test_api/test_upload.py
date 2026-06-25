"""Tests for upload API endpoints (upload / confirm / import)."""

from fastapi.testclient import TestClient
from app.main import app

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

    # ------------------------------------------------------------------
    # Dedup tests
    # ------------------------------------------------------------------

    def test_upload_duplicate_file_returns_409(self, client):
        """上传内容完全相同的文件应返回 409"""
        headers = get_auth_header(client)

        # 第一次上传
        r1 = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("dup.csv", QMT_CSV, "text/csv")},
        )
        assert r1.status_code == 200

        # 第二次上传相同内容（文件名不同）
        r2 = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("dup_renamed.csv", QMT_CSV, "text/csv")},
        )
        assert r2.status_code == 409
        assert "已上传过" in r2.json()["detail"]

    def test_import_skips_duplicate_trades(self, client):
        """导入与已有交易重复的数据时，应跳过并返回正确计数"""
        headers = get_auth_header(client)

        # 第一次上传 + 导入
        r1 = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("batch1.csv", QMT_CSV, "text/csv")},
        )
        fid1 = r1.json()["raw_file_id"]
        client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": fid1, "source_type": "smart"},
        )
        imp1 = client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": fid1},
        )
        assert imp1.json()["imported_count"] == 4
        assert imp1.json()["skipped_count"] == 0

        # 第二次上传：内容不同（多一个换行）但交易记录相同
        # 换行可绕过文件级 SHA256 去重
        slightly_different = QMT_CSV + "\n"
        r2 = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("batch2.csv", slightly_different, "text/csv")},
        )
        fid2 = r2.json()["raw_file_id"]
        client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": fid2, "source_type": "smart"},
        )
        imp2 = client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": fid2},
        )
        assert imp2.json()["imported_count"] == 0
        assert imp2.json()["skipped_count"] == 4

    def test_import_partial_duplicate_trades(self, client):
        """部分重复：新交易写入，重复交易跳过"""
        headers = get_auth_header(client)

        # 先导入 4 笔
        r1 = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("p1.csv", QMT_CSV, "text/csv")},
        )
        fid1 = r1.json()["raw_file_id"]
        client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": fid1, "source_type": "smart"},
        )
        client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": fid1},
        )

        # 再导入含 2 笔重复 + 2 笔新交易的数据
        mixed_csv = (
            "委托时间,证券代码,证券名称,买卖方向,成交价格,成交数量,手续费\n"
            "2024-01-05 09:30:00,000001,平安银行,买入,10.50,1000,5.00\n"   # 重复
            "2024-01-10 14:00:00,000001,平安银行,卖出,11.00,1000,5.00\n"   # 重复
            "2024-03-01 09:30:00,000002,万科A,买入,15.00,500,2.50\n"       # 新
            "2024-03-05 14:00:00,000002,万科A,卖出,16.00,500,2.50"          # 新
        )
        r2 = client.post(
            "/api/upload",
            headers=headers,
            files={"file": ("p2.csv", mixed_csv, "text/csv")},
        )
        fid2 = r2.json()["raw_file_id"]
        client.post(
            "/api/upload/confirm",
            headers=headers,
            json={"raw_file_id": fid2, "source_type": "smart"},
        )
        imp2 = client.post(
            "/api/upload/import",
            headers=headers,
            json={"raw_file_id": fid2},
        )
        assert imp2.json()["imported_count"] == 2
        assert imp2.json()["skipped_count"] == 2

    def test_different_users_same_file_no_conflict(self, client):
        """不同用户上传相同文件互不干扰"""
        # 用户 A 注册 + 上传（使用主 client）
        headers_a = get_auth_header(client)

        # 用户 B 注册——使用独立的 TestClient 避免 cookie 串扰
        # 注意：auth 组件 _OAuth2WithCookie 优先读取 cookie 而非 Authorization header，
        # 在同一 client 实例上，第二次 register 会覆盖第一次的 cookie，
        # 导致后续请求以第二个用户的身份执行。
        client_b = TestClient(app)
        resp_b = client_b.post(
            "/api/auth/register",
            json={"email": "user_b@test.com", "password": "Test1234"},
        )
        assert resp_b.status_code == 201
        token_b = resp_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # A 上传
        r_a = client.post(
            "/api/upload",
            headers=headers_a,
            files={"file": ("shared.csv", QMT_CSV, "text/csv")},
        )
        assert r_a.status_code == 200

        # B 上传相同内容——应有自己的独立 RawFile
        r_b = client_b.post(
            "/api/upload",
            headers=headers_b,
            files={"file": ("shared.csv", QMT_CSV, "text/csv")},
        )
        assert r_b.status_code == 200  # 不同用户，不冲突
