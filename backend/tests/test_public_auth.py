"""Public patient auth tests (Plan/02 §8)."""

from tests.conftest import csrf_headers

REGISTER = {"full_name": "Patient One", "email": "p1@example.com", "password": "passw0rd"}


def register(client, payload=None, headers=None):
    merged = csrf_headers(client)
    merged.update(headers or {})
    return client.post("/api/public/auth/register", json=payload or REGISTER, headers=merged)


def test_register_email_ok(client):
    resp = register(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "p1@example.com"
    assert "hmsv2_refresh" in client.cookies


def test_register_phone_only_ok(client):
    resp = register(client, {"full_name": "P2", "phone": "01012345678", "password": "passw0rd"})
    assert resp.status_code == 200
    assert resp.json()["user"]["phone"] == "01012345678"


def test_register_requires_identifier(client):
    resp = register(client, {"full_name": "P3", "password": "passw0rd"})
    assert resp.status_code == 422


def test_register_duplicate_409(client):
    register(client)
    resp = register(client)
    assert resp.status_code == 409


def test_register_idempotent_replay(client):
    key = "reg-key-123"
    payload = {
        "full_name": "Idem",
        "email": "idem@example.com",
        "password": "passw0rd",
    }
    first = register(client, payload, headers={"Idempotency-Key": key})
    second = register(client, payload, headers={"Idempotency-Key": key})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["access_token"] == second.json()["access_token"]


def test_register_key_reuse_different_body_409(client):
    payload = {
        "full_name": "Idem2",
        "email": "idem2@example.com",
        "password": "passw0rd",
    }
    register(client, payload, headers={"Idempotency-Key": "reg-key-x"})
    resp = register(
        client,
        {"full_name": "Different", "email": "idem2@example.com", "password": "passw0rd"},
        headers={"Idempotency-Key": "reg-key-x"},
    )
    assert resp.status_code == 409


def test_patient_login_and_me(client):
    register(client, {"full_name": "Login", "email": "login@example.com", "password": "passw0rd"})
    resp = client.post(
        "/api/public/auth/login",
        json={"email_or_phone": "login@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get("/api/public/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "login@example.com"


def test_patient_login_wrong_password(client):
    register(client, {"full_name": "Wrong", "email": "wrong@example.com", "password": "passw0rd"})
    resp = client.post(
        "/api/public/auth/login",
        json={"email_or_phone": "wrong@example.com", "password": "wrongpass"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 401


def test_patient_refresh_and_logout(client):
    register(
        client,
        {"full_name": "Refresh", "email": "refresh@example.com", "password": "passw0rd"},
    )
    assert client.post("/api/public/auth/refresh", headers=csrf_headers(client)).status_code == 200
    assert client.post("/api/public/auth/logout", headers=csrf_headers(client)).status_code == 204
    assert client.post("/api/public/auth/refresh", headers=csrf_headers(client)).status_code == 401
