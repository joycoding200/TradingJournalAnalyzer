"""Tests for JWT auth (register + login)."""


def test_register_and_login(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "test@example.com", "password": "secret123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    resp = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_register_duplicate_email(client):
    client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "secret123"},
    )
    resp = client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "secret123"},
    )
    assert resp.status_code == 409


def test_login_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={"email": "wrong@example.com", "password": "secret123"},
    )
    resp = client.post(
        "/api/auth/login",
        json={"email": "wrong@example.com", "password": "badpass"},
    )
    assert resp.status_code == 401


def test_protected_route_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 403


def test_invalid_token(client):
    resp = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer invalid_token_here"}
    )
    assert resp.status_code == 401
