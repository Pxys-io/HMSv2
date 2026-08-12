"""Financial tests (Plan/06 §6): M1 resolution, per-hour, auto-invoice,
discounts/caps, installments, immutability, refunds, idempotency, reports."""

import secrets
from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import Invoice
from app.models.identity import PatientProfile
from tests.conftest import csrf_headers

TODAY = date.today()


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


def _book_and_check_in(client, clinic, headers):
    """Books, checks in, and starts a visit; returns the queue entry."""
    client.post(
        "/api/appointments",
        json={"patient_profile_id": clinic["profile_id"], "doctor_id": clinic["doctor_id"],
              "visit_type_id": clinic["visit_type_id"], "date": TODAY.isoformat(),
              "start_time": "17:00"},
        headers={**headers, "Idempotency-Key": f"bk-{secrets.token_hex(4)}"},
    )
    client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment_id"]},
        headers={**headers, "Idempotency-Key": f"ci-{secrets.token_hex(4)}"},
    )
    entry = client.get(
        f"/api/queue?doctor_id={clinic['doctor_id']}&date={TODAY.isoformat()}",
        headers=headers,
    ).json()["entries"][0]
    client.post(
        f"/api/queue/{entry['id']}/start",
        headers={**headers, "Idempotency-Key": f"st-{secrets.token_hex(4)}"},
    )
    return entry


def _complete_visit(client, clinic, token=None):
    """Books, checks in, starts, and completes a visit -> auto-invoice."""
    admin = admin_headers(client)
    headers = {"Authorization": f"Bearer {token or clinic['token']}"}
    client.post(
        "/api/appointments",
        json={"patient_profile_id": clinic["profile_id"], "doctor_id": clinic["doctor_id"],
              "visit_type_id": clinic["visit_type_id"], "date": TODAY.isoformat(),
              "start_time": "17:00"},
        headers={**admin, "Idempotency-Key": f"bk-{secrets.token_hex(4)}"},
    )
    client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment_id"]},
        headers={**admin, "Idempotency-Key": f"ci-{secrets.token_hex(4)}"},
    )
    entry = client.get(
        f"/api/queue?doctor_id={clinic['doctor_id']}&date={TODAY.isoformat()}", headers=admin
    ).json()["entries"][0]
    client.post(
        f"/api/queue/{entry['id']}/start",
        headers={**admin, "Idempotency-Key": f"st-{secrets.token_hex(4)}"},
    )
    visit_id = client.get(
        f"/api/patients/{clinic['profile_id']}/timeline", headers=headers
    ).json()[0]["id"]
    resp = client.post(
        f"/api/visits/{visit_id}/complete",
        headers={**headers, "Idempotency-Key": f"cp-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200
    return visit_id


def _invoice_visit(client, admin, visit_id):
    """Cashier bills a completed visit (the manual flow)."""
    resp = client.post(
        f"/api/invoices/from-visit/{visit_id}",
        headers={**admin, "Idempotency-Key": f"inv-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _invoice_for_visit(client, admin, visit_id):
    rows = client.get("/api/invoices", headers=admin).json()["items"]
    return next(i for i in rows if i["visit_id"] == visit_id)


def test_no_auto_invoice_on_complete(client, clinic):
    """Visits complete without an invoice — the cashier decides (user decision)."""
    visit_id = _complete_visit(client, clinic)
    db = SessionLocal()
    count = len(db.scalars(select(Invoice).where(Invoice.visit_id == visit_id)).all())
    db.close()
    assert count == 0
    # completing again still 409 (visit lifecycle unchanged)
    resp = client.post(
        f"/api/visits/{visit_id}/complete",
        headers={"Authorization": f"Bearer {clinic['token']}", "Idempotency-Key": "dup-1"},
    )
    assert resp.status_code == 409


def test_cashier_invoices_completed_visit(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)

    # appears in the uninvoiced list with a price preview
    uninvoiced = client.get("/api/cashier/uninvoiced", headers=admin).json()
    row = next(r for r in uninvoiced if r["visit_id"] == visit_id)
    assert row["price_preview"] == 300.0
    assert row["type_name"] == "Consultation"

    # cashier creates the invoice
    invoice = _invoice_visit(client, admin, visit_id)
    assert invoice["number"].startswith(f"INV-{date.today().year}-")
    assert invoice["total"] == 300.0
    assert invoice["patient_due"] == 300.0
    assert invoice["status"] == "issued"

    # no longer uninvoiced; double-invoice -> 409
    uninvoiced = client.get("/api/cashier/uninvoiced", headers=admin).json()
    assert all(r["visit_id"] != visit_id for r in uninvoiced)
    again = client.post(f"/api/invoices/from-visit/{visit_id}", headers=admin)
    assert again.status_code == 409


def test_discount_caps_and_recompute(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = _invoice_for_visit(client, admin, visit_id)

    # secretary login
    sec_token = client.post(
        "/api/auth/login", json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    sec = {"Authorization": f"Bearer {sec_token}"}

    over = client.post(
        f"/api/invoices/{invoice['id']}/discount",
        json={"kind": "percent", "value": 15},
        headers=sec,
    )
    assert over.status_code == 403  # cap is 10%

    ok = client.post(
        f"/api/invoices/{invoice['id']}/discount",
        json={"kind": "percent", "value": 10, "reason": "loyalty"},
        headers=sec,
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["discount_total"] == 30.0
    assert body["total"] == 270.0
    assert body["patient_due"] == 270.0

    # discount cannot exceed patient share (admin bypasses the cap)
    too_much = client.post(
        f"/api/invoices/{invoice['id']}/discount",
        json={"kind": "fixed", "value": 300},
        headers=admin,
    )
    assert too_much.status_code == 422


def test_installments_and_overpay(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = _invoice_for_visit(client, admin, visit_id)
    url = f"/api/invoices/{invoice['id']}/payments"

    first = client.post(url, json={"amount": 100, "method": "cash"},
                        headers={**admin, "Idempotency-Key": "pay-1"})
    assert first.status_code == 200
    assert first.json()["status"] == "partially_paid"

    second = client.post(url, json={"amount": 100, "method": "instapay", "reference": "ip-1"},
                         headers={**admin, "Idempotency-Key": "pay-2"})
    assert second.status_code == 200
    assert second.json()["status"] == "partially_paid"

    third = client.post(url, json={"amount": 100, "method": "cash"},
                        headers={**admin, "Idempotency-Key": "pay-3"})
    assert third.status_code == 200
    assert third.json()["status"] == "paid"
    assert third.json()["remaining"] == 0

    # overpay -> 409
    over = client.post(url, json={"amount": 10, "method": "cash"},
                       headers={**admin, "Idempotency-Key": "pay-4"})
    assert over.status_code == 409

    # idempotent replay of a payment
    replay = client.post(url, json={"amount": 100, "method": "cash"},
                         headers={**admin, "Idempotency-Key": "pay-3"})
    assert replay.status_code == 200
    assert replay.json()["id"] == third.json()["id"]

    # frozen after payment: adding an item -> 409
    frozen = client.post(
        f"/api/invoices/{invoice['id']}/items",
        json={"description": "extra", "qty": 1, "unit_price": 50},
        headers=admin,
    )
    assert frozen.status_code == 409


def test_refund_full_marks_refunded(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = _invoice_for_visit(client, admin, visit_id)
    payment = client.post(
        f"/api/invoices/{invoice['id']}/payments",
        json={"amount": 300, "method": "cash"},
        headers={**admin, "Idempotency-Key": "rf-1"},
    ).json()["payments"][-1]

    refund = client.post(
        f"/api/payments/{payment['id']}/refund",
        json={},
        headers={**admin, "Idempotency-Key": "rf-2"},
    )
    assert refund.status_code == 200
    body = refund.json()
    assert body["status"] == "refunded"
    assert body["refunded_total"] == 300.0
    assert body["net_paid"] == 0.0

    # over-refund -> 409
    again = client.post(
        f"/api/payments/{payment['id']}/refund",
        json={"amount": 100},
        headers={**admin, "Idempotency-Key": "rf-3"},
    )
    assert again.status_code == 409


def test_cancel_reissue_linked_pair(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = _invoice_for_visit(client, admin, visit_id)
    resp = client.post(
        f"/api/invoices/{invoice['id']}/cancel-reissue", headers=admin
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reissued"].startswith("INV-")

    db = SessionLocal()
    new_inv = db.scalar(
        select(Invoice).where(Invoice.number == body["reissued"])
    )
    assert new_inv.reissue_of_id == invoice["id"]
    assert new_inv.status == "issued"
    old = db.get(Invoice, invoice["id"])
    assert old.status == "cancelled"
    db.close()


def test_syndicate_price_and_balance(client, clinic):
    admin = admin_headers(client)
    created = client.post(
        "/api/syndicates",
        json={"name": "Teachers Syndicate", "name_ar": "نقابة المعلمين", "code": "TEA"},
        headers=admin,
    )
    assert created.status_code == 200
    syndicate_id = created.json()["id"]
    client.put(
        f"/api/syndicates/{syndicate_id}/prices",
        json={"items": [{"visit_type_id": clinic["visit_type_id"], "syndicate_coverage": 200,
                         "patient_share": 50}]},
        headers=admin,
    )
    # assign the patient to the syndicate

    db = SessionLocal()
    profile = db.get(PatientProfile, clinic["profile_id"])
    profile.syndicate_id = syndicate_id
    db.commit()
    db.close()

    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = _invoice_for_visit(client, admin, visit_id)
    assert invoice["total"] == 250.0  # coverage + share
    assert invoice["syndicate_due"] == 200.0
    assert invoice["patient_due"] == 50.0

    report = client.get("/api/reports/syndicate-balances", headers=admin).json()
    row = next(r for r in report["rows"] if r["syndicate_id"] == syndicate_id)
    assert row["accrued_balance"] == 200.0


def test_reports_and_csv(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = _invoice_for_visit(client, admin, visit_id)
    client.post(
        f"/api/invoices/{invoice['id']}/payments",
        json={"amount": 300, "method": "fawry"},
        headers={**admin, "Idempotency-Key": "rep-1"},
    )

    today = date.today().isoformat()
    revenue = client.get(
        f"/api/reports/daily-revenue?from={today}&to={today}", headers=admin
    ).json()
    fawry_net = sum(r["net"] for r in revenue["rows"] if r["method"] == "fawry")
    assert fawry_net == 300.0  # this test's payment only (other tests coexist)

    share = client.get(f"/api/reports/doctor-share?from={today}&to={today}", headers=admin).json()
    row = next(r for r in share["rows"] if r["doctor_id"] == clinic["doctor_id"])
    assert row["visits"] == 1
    assert row["invoiced"] == 300.0
    assert row["collected"] == 300.0

    csv_resp = client.get(
        f"/api/reports/daily-revenue?from={today}&to={today}&format=csv", headers=admin
    )
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "date,method,net" in csv_resp.text


def test_cashier_price_adjust_permission_gate(client, clinic):
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = _invoice_for_visit(client, admin, visit_id)
    item_id = invoice["items"][0]["id"]

    sec_token = client.post(
        "/api/auth/login", json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    sec = {"Authorization": f"Bearer {sec_token}"}

    # setting off by default -> cashier denied
    denied = client.patch(
        f"/api/invoices/{invoice['id']}/items/{item_id}",
        json={"unit_price": 250},
        headers=sec,
    )
    assert denied.status_code == 403

    # admin always allowed
    adjusted = client.patch(
        f"/api/invoices/{invoice['id']}/items/{item_id}",
        json={"unit_price": 250},
        headers=admin,
    )
    assert adjusted.status_code == 200
    body = adjusted.json()
    assert body["subtotal"] == 250.0
    assert body["patient_due"] == 250.0
    assert body["items"][0]["unit_price"] == 250.0

    # admin enables the setting -> cashier allowed
    client.put("/api/settings", json={"billing.cashier_can_adjust_pricing": True}, headers=admin)
    ok = client.patch(
        f"/api/invoices/{invoice['id']}/items/{item_id}",
        json={"qty": 2},
        headers=sec,
    )
    assert ok.status_code == 200
    assert ok.json()["subtotal"] == 500.0
    client.put("/api/settings", json={"billing.cashier_can_adjust_pricing": False}, headers=admin)

    # frozen after payment
    paid = client.post(
        f"/api/invoices/{invoice['id']}/payments",
        json={"amount": 500, "method": "cash"},
        headers={**admin, "Idempotency-Key": "adj-1"},
    )
    assert paid.status_code == 200
    frozen = client.patch(
        f"/api/invoices/{invoice['id']}/items/{item_id}",
        json={"unit_price": 100},
        headers=admin,
    )
    assert frozen.status_code == 409


def test_billing_permissions_endpoint(client, clinic):
    admin = admin_headers(client)
    sec_token = client.post(
        "/api/auth/login", json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]

    sec_perm = client.get(
        "/api/billing/permissions", headers={"Authorization": f"Bearer {sec_token}"}
    ).json()
    assert sec_perm["cashier_can_adjust_pricing"] is False
    assert sec_perm["discount_cap_secretary_pct"] == 10

    admin_perm = client.get("/api/billing/permissions", headers=admin).json()
    assert admin_perm["cashier_can_adjust_pricing"] is True
