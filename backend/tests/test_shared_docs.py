"""Patient-accessible documents tests (Plan/14 C10)."""

import secrets

from tests.conftest import csrf_headers
from tests.test_financial import _complete_visit, admin_headers


def _register_patient(client, email):
    resp = client.post(
        "/api/public/auth/register",
        json={"full_name": "Doc Owner", "email": email, "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _attach_account(client, admin, profile_id, account_id):
    from app.db.session import SessionLocal
    from app.models.identity import PatientProfile

    db = SessionLocal()
    profile = db.get(PatientProfile, profile_id)
    profile.account_id = account_id
    db.commit()
    db.close()


def test_share_and_patient_open_document(client, clinic):
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]

    # staff shares a report with the patient
    resp = client.post(
        f"/api/visits/{visit_id}/documents/share?key=report",
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]

    # patient account sees it under "My documents"
    account = _register_patient(client, f"own-{secrets.token_hex(4)}@example.com")
    _attach_account(client, admin, clinic["profile_id"], account["user"]["id"])
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    items = client.get("/api/patient/documents", headers=headers).json()["items"]
    assert len(items) == 1
    assert items[0]["doc_key"] == "report"
    assert items[0]["visit_id"] == visit_id

    # the token opens the rendered document
    resp = client.get(
        f"/api/patient/documents/report/{visit_id}?token={token}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]
    assert "Dr." in resp.text or "Patient" in resp.text


def test_unshared_document_forbidden(client, clinic):
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=admin
    ).json()[0]["id"]
    account = _register_patient(client, f"own2-{secrets.token_hex(4)}@example.com")
    _attach_account(client, admin, clinic["profile_id"], account["user"]["id"])
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    resp = client.get(
        f"/api/patient/documents/rx/{visit_id}?token=whatever", headers=headers
    )
    assert resp.status_code == 403


def test_share_requires_permission(client, clinic):
    _complete_visit(client, clinic)
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline",
        headers={"Authorization": f"Bearer {clinic['token']}"},
    ).json()[0]["id"]
    resp = client.post(
        f"/api/visits/{visit_id}/documents/share?key=report",
        headers={"Authorization": f"Bearer {clinic['token']}"},
    )
    # doctor role has emr.share_doc -> allowed
    assert resp.status_code == 200, resp.text
