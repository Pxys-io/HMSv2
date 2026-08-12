"""Activity stream tests (Plan/14 C2)."""

import secrets

from tests.test_financial import _complete_visit, _invoice_visit, admin_headers


def test_patient_create_and_update_activity(client, clinic):
    admin = admin_headers(client)
    resp = client.post(
        "/api/patients",
        json={"full_name": "Act One", "phone": "010123456"},
        headers={**admin, "Idempotency-Key": f"pa-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    client.patch(
        f"/api/patients/{pid}/demographics",
        json={"phone": "0102"},
        headers=admin,
    )
    events = client.get(f"/api/patients/{pid}/activity", headers=admin).json()["items"]
    types = [e["type"] for e in events]
    assert "patient.created" in types
    assert "patient.updated" in types
    updated = next(e for e in events if e["type"] == "patient.updated")
    assert "phone" in updated["data"]["fields"]


def test_appointment_flow_activity(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = client.get("/api/invoices?limit=5", headers=admin).json()["items"][0]
    client.post(
        f"/api/invoices/{invoice['id']}/payments",
        json={"amount": 300.0, "method": "cash"},
        headers={**admin, "Idempotency-Key": f"pay-{secrets.token_hex(4)}"},
    )
    pid = clinic["profile_id"]
    events = client.get(f"/api/patients/{pid}/activity?limit=50", headers=admin).json()["items"]
    types = [e["type"] for e in events]
    for expected in (
        "appointment.booked",
        "appointment.checked_in",
        "visit.created",
        "visit.completed",
        "payment.received",
    ):
        assert expected in types, types


def test_activity_append_only_and_pagination(client, clinic):
    admin = admin_headers(client)
    _complete_visit(client, clinic)
    pid = clinic["profile_id"]
    total = client.get(f"/api/patients/{pid}/activity?limit=200", headers=admin).json()
    assert len(total["items"]) >= 3
    short = client.get(f"/api/patients/{pid}/activity?limit=1", headers=admin).json()
    assert len(short["items"]) == 1
    assert short["items"][0]["id"] >= total["items"][0]["id"]
