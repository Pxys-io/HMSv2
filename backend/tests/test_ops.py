"""Referral + lab order tests (Plan/14 C6, C7)."""

import secrets
from datetime import date

from tests.test_financial import admin_headers

TODAY = date.today()


def test_referral_lifecycle(client, clinic):
    admin = admin_headers(client)
    pid = clinic["profile_id"]
    resp = client.post(
        "/api/referrals",
        json={"patient_profile_id": pid, "from_doctor_id": clinic["doctor_id"],
              "to_text": "Dr. Mahmoud - Cardiology", "place": "Cairo Heart Center",
              "referral_date": TODAY.isoformat()},
        headers={**admin, "Idempotency-Key": f"ref-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    rid = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    rows = client.get("/api/referrals?status=pending", headers=admin).json()["items"]
    assert any(r["id"] == rid for r in rows)

    # secretary records the outcome
    resp = client.patch(
        f"/api/referrals/{rid}",
        json={"outcome": "Patient seen, treatment started",
              "outcome_seen_at": TODAY.isoformat()},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "seen"
    assert resp.json()["outcome_text"] == "Patient seen, treatment started"

    rows = client.get("/api/referrals?status=seen", headers=admin).json()["items"]
    assert any(r["id"] == rid for r in rows)


def test_referral_requires_patient(client, clinic):
    admin = admin_headers(client)
    resp = client.post("/api/referrals", json={"to_text": "x"}, headers=admin)
    assert resp.status_code == 422


def test_lab_order_lifecycle(client, clinic):
    admin = admin_headers(client)
    pid = clinic["profile_id"]
    resp = client.post(
        "/api/lab-orders",
        json={"patient_profile_id": pid, "doctor_id": clinic["doctor_id"],
              "lab_name": "Alfa Lab", "tests": ["CBC", "HbA1c"],
              "order_date": TODAY.isoformat()},
        headers={**admin, "Idempotency-Key": f"lab-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    oid = resp.json()["id"]
    assert resp.json()["tests"] == ["CBC", "HbA1c"]

    rows = client.get("/api/lab-orders?status=pending", headers=admin).json()["items"]
    assert any(r["id"] == oid for r in rows)

    # secretary marks received; doctor attaches results and closes
    client.patch(f"/api/lab-orders/{oid}", json={"status": "received"}, headers=admin)
    resp = client.patch(f"/api/lab-orders/{oid}",
                        json={"status": "done", "results_attachment_id": 7},
                        headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["results_attachment_id"] == 7

    rows = client.get("/api/lab-orders?status=done", headers=admin).json()["items"]
    assert any(r["id"] == oid for r in rows)


def test_lab_order_requires_tests(client, clinic):
    admin = admin_headers(client)
    resp = client.post(
        "/api/lab-orders",
        json={"patient_profile_id": clinic["profile_id"], "lab_name": "X", "tests": []},
        headers=admin,
    )
    assert resp.status_code == 422
