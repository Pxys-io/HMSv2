"""Dashboard + KPI tests (Plan/14 C1)."""

import secrets
from datetime import date, timedelta

from tests.test_financial import _complete_visit, _invoice_visit, admin_headers

TODAY = date.today()


def test_overview_counts(client, clinic):
    admin = admin_headers(client)
    overview = client.get("/api/dashboard/overview", headers=admin).json()
    base_seen = overview["seen"]
    base_waiting = overview["waiting"]

    visit_id = _complete_visit(client, clinic)
    _invoice_visit(client, admin, visit_id)
    invoice = client.get(f"/api/invoices?visit_id={visit_id}", headers=admin)
    row = invoice.json()["items"][0]
    client.post(
        f"/api/invoices/{row['id']}/payments",
        json={"amount": 300.0, "method": "cash"},
        headers={**admin, "Idempotency-Key": f"pay-{secrets.token_hex(4)}"},
    )

    overview = client.get("/api/dashboard/overview", headers=admin).json()
    assert overview["seen"] == base_seen + 1
    assert overview["waiting"] == base_waiting
    assert overview["revenue_today"] >= 300.0


def test_kpis_respond(client, clinic):
    admin = admin_headers(client)
    from_d = (TODAY - timedelta(days=7)).isoformat()
    to_d = (TODAY + timedelta(days=7)).isoformat()
    kpis = client.get(f"/api/dashboard/kpis?from={from_d}&to={to_d}", headers=admin).json()
    assert "appointments" in kpis
    assert kpis["appointments"]["total"] >= 0
    assert 0 <= kpis["no_show_rate"] <= 100
    assert 0 <= kpis["collection_rate"] <= 100
    assert kpis["new_patients"] >= 0
    assert kpis["visits"] >= 0


def test_kpis_invalid_range(client, clinic):
    admin = admin_headers(client)
    resp = client.get(
        "/api/dashboard/kpis?from=2026-01-10&to=2026-01-01", headers=admin
    )
    assert resp.status_code == 422


def test_overview_requires_permission(client, clinic):
    """Doctor role has ops.dashboard and may read the overview."""
    token = clinic["token"]
    assert client.get("/api/dashboard/overview", headers={
        "Authorization": f"Bearer {token}"}).status_code == 200
