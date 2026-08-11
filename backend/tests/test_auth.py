"""Staff auth tests (Plan/02 §8)."""

from tests.conftest import csrf_headers


def login(client, email="admin@example.com", password="passw0rd"):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )


def test_login_ok(client, admin_user):
    resp = login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["role"] == "admin"
    assert "hmsv2_refresh" in client.cookies
    assert "hmsv2_csrf" in client.cookies


def test_login_wrong_password(client, admin_user):
    resp = login(client, password="wrongpass")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHORIZED"


def test_login_inactive_user(client, db):
    from tests.conftest import make_staff

    make_staff(db, email="off@example.com", is_active=False)
    resp = login(client, email="off@example.com")
    assert resp.status_code == 401


def test_me_with_bearer(client, admin_user):
    token = login(client).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@example.com"


def test_refresh_rotates_and_revokes_family(client, admin_user):
    from fastapi.testclient import TestClient

    login(client)
    old_refresh = client.cookies["hmsv2_refresh"]
    csrf = client.cookies["hmsv2_csrf"]
    csrf_headers = {"X-CSRF-Token": csrf}

    resp = client.post("/api/auth/refresh", headers=csrf_headers)
    assert resp.status_code == 200
    new_refresh = client.cookies["hmsv2_refresh"]

    # Reuse of the rotated token = theft: the whole family is revoked.
    stale = TestClient(
        client.app, cookies={"hmsv2_refresh": old_refresh, "hmsv2_csrf": csrf}
    )
    assert stale.post("/api/auth/refresh", headers=csrf_headers).status_code == 401

    # The freshly rotated token is dead too (family revocation).
    newer = TestClient(
        client.app, cookies={"hmsv2_refresh": new_refresh, "hmsv2_csrf": csrf}
    )
    assert newer.post("/api/auth/refresh", headers=csrf_headers).status_code == 401


def test_logout_revokes_refresh(client, admin_user):
    login(client)
    resp = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert resp.status_code == 204
    resp = client.post("/api/auth/refresh", headers=csrf_headers(client))
    assert resp.status_code == 401


def test_login_lockout_after_10_failures(client, db):
    from tests.conftest import make_staff

    make_staff(db, email="lock@example.com")
    for _ in range(10):
        login(client, email="lock@example.com", password="wrongpass")
    resp = login(client, email="lock@example.com", password="wrongpass")
    assert resp.status_code == 429


def test_role_guard_secretary_cannot_list_users(client, admin_user, secretary_user):
    sec_token = client.post(
        "/api/auth/login",
        json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    resp = client.get("/api/users", headers={"Authorization": f"Bearer {sec_token}"})
    assert resp.status_code == 403

    admin_token = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    resp = client.get("/api/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200


def test_admin_create_user_audited(client, admin_user):
    import secrets

    from sqlalchemy import select

    from app.audit.models import AuditEvent
    from app.db.session import AuditSessionLocal

    email = f"new-{secrets.token_hex(4)}@example.com"
    token = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    resp = client.post(
        "/api/users",
        json={"email": email, "password": "passw0rd", "full_name": "New", "role": "secretary"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    user_id = str(resp.json()["id"])

    with AuditSessionLocal() as audit_db:
        events = audit_db.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "user.create", AuditEvent.entity_id == user_id
            )
        ).all()
        intents = [e for e in events if e.outcome == "intent"]
        commits = [e for e in events if e.outcome == "committed"]
        assert len(intents) == 1
        assert len(commits) == 1
        assert intents[0].correlation_id == commits[0].correlation_id
