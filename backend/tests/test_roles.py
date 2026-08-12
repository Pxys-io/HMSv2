"""Roles & permissions tests (Plan/14 A1)."""

import secrets

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.identity import Role, StaffUser
from tests.conftest import csrf_headers


def admin_headers(client):
    client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    token = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_system_roles_seeded_with_matrix(client):
    headers = admin_headers(client)
    roles = client.get("/api/roles", headers=headers).json()
    by_name = {r["name"]: r for r in roles}
    assert set(by_name) == {"admin", "doctor", "secretary"}
    assert by_name["admin"]["is_system"] is True
    # admin holds every permission
    perms = client.get("/api/permissions", headers=headers).json()
    all_codes = [p["code"] for g in perms["groups"] for p in g["permissions"]]
    assert set(by_name["admin"]["permissions"]) == set(all_codes)
    # doctor cannot touch patients edit? doctor HAS patient.edit; secretary lacks emr
    assert "emr.view" not in by_name["secretary"]["permissions"]
    assert "billing.payment" in by_name["secretary"]["permissions"]
    assert "report.all" not in by_name["doctor"]["permissions"]
    assert "report.own" in by_name["doctor"]["permissions"]


def test_custom_cashier_role_scenario(client):
    """Plan/14 A1 done-when: a 'cashier' role with only billing view/payment/
    expense sees only cashier capabilities and is 403 on /api/patients."""
    headers = admin_headers(client)
    created = client.post(
        "/api/roles", json={"name": f"cashier-{secrets.token_hex(4)}"}, headers=headers
    )
    assert created.status_code == 200
    role_id = created.json()["id"]

    # grant billing.view + billing.payment + billing.expense
    perms = client.get("/api/permissions", headers=headers).json()
    wanted = {
        p["id"]
        for g in perms["groups"]
        for p in g["permissions"]
        if p["code"] in ("billing.view", "billing.payment", "billing.expense")
    }
    assert len(wanted) == 3
    updated = client.put(
        f"/api/roles/{role_id}/permissions",
        json={"permission_ids": sorted(wanted)},
        headers=headers,
    )
    assert updated.status_code == 200

    # create a staff user with the cashier role
    email = f"cashier-{secrets.token_hex(4)}@example.com"
    user = client.post(
        "/api/users",
        json={
            "email": email,
            "password": "passw0rd",
            "full_name": "Cashier",
            "role_id": role_id,
        },
        headers=headers,
    )
    assert user.status_code == 200
    assert user.json()["role"] == "custom"

    token = client.post(
        "/api/auth/login", json={"email": email, "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    # 403 on patients (no patient.view), OK on billing list (billing.view)
    assert client.get("/api/patients/1", headers=auth).status_code == 403
    assert client.get("/api/invoices?page_size=5", headers=auth).status_code == 200
    # cashier cannot refund (no billing.refund)
    assert client.get("/api/billing/permissions", headers=auth).status_code == 200
    assert client.get("/api/audit/events", headers=auth).status_code == 403


def test_system_role_name_locked(client):
    headers = admin_headers(client)
    db = SessionLocal()
    admin_role = db.scalar(select(Role).where(Role.name == "admin"))
    db.close()
    resp = client.patch(f"/api/roles/{admin_role.id}", json={"name": "boss"}, headers=headers)
    assert resp.status_code == 409


def test_user_role_assignment_and_doctor_guard(client):
    headers = admin_headers(client)
    email = f"swap-{secrets.token_hex(4)}@example.com"
    created = client.post(
        "/api/users",
        json={"email": email, "password": "passw0rd", "full_name": "Swap", "role": "doctor"},
        headers=headers,
    )
    assert created.status_code == 200
    user_id = created.json()["id"]
    assert created.json()["role"] == "doctor"

    db = SessionLocal()
    sec_role = db.scalar(select(Role).where(Role.name == "secretary"))
    db.close()
    swapped = client.patch(
        f"/api/users/{user_id}",
        json={"role_id": sec_role.id},
        headers=headers,
    )
    assert swapped.status_code == 200
    assert swapped.json()["role"] == "secretary"


def test_permission_guard_regression_system_roles(client):
    """Secretary hitting admin-only routes still 403; doctor hitting refund still 403."""
    sec_token = client.post(
        "/api/auth/login", json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    sec = {"Authorization": f"Bearer {sec_token}"}
    assert client.get("/api/roles", headers=sec).status_code == 403
    assert client.get("/api/settings", headers=sec).status_code == 403
    assert client.get("/api/audit/events", headers=sec).status_code == 403

    db = SessionLocal()
    from app.core.security import hash_password

    doc_user = StaffUser(
        email=f"dr-{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("passw0rd"), full_name="D",
        role_id=db.scalar(select(Role).where(Role.name == "doctor")).id,
        is_active=True,
    )
    db.add(doc_user)
    db.commit()
    db.close()
    doc_token = client.post(
        "/api/auth/login", json={"email": doc_user.email, "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    doc = {"Authorization": f"Bearer {doc_token}"}
    assert client.get("/api/roles", headers=doc).status_code == 403
    assert client.get("/api/audit/events", headers=doc).status_code == 403
