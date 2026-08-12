"""VAT tests (Plan/14 A3): snapshot, inclusive/exclusive math, exemption,
snapshot immutability, item + payment behaviour under tax."""

import secrets

import pytest

from tests.test_financial import _complete_visit, _invoice_visit, admin_headers


def _set_setting(client, admin, key, value):
    resp = client.put("/api/settings", json={key: value}, headers=admin)
    assert resp.status_code == 200, resp.text


@pytest.fixture()
def vat(client):
    admin = admin_headers(client)
    _set_setting(client, admin, "billing.vat_rate_pct", 15)
    _set_setting(client, admin, "billing.vat_inclusive", False)
    _set_setting(client, admin, "billing.vat_exempt", False)
    _set_setting(client, admin, "billing.vat_number", "EG-100-001")
    yield admin
    _set_setting(client, admin, "billing.vat_rate_pct", 0)
    _set_setting(client, admin, "billing.vat_inclusive", True)
    _set_setting(client, admin, "billing.vat_exempt", False)


def test_exclusive_vat_math(client, clinic, vat):
    """15% exclusive -> total = subtotal x 1.15 with a tax line on the invoice."""
    visit_id = _complete_visit(client, clinic)
    invoice = _invoice_visit(client, vat, visit_id)
    assert invoice["subtotal"] == 300.0
    assert invoice["tax_rate"] == 15
    assert invoice["tax_total"] == 45.0
    assert invoice["total"] == 345.0
    assert invoice["patient_due"] == 345.0
    assert invoice["vat_inclusive"] is False
    assert invoice["vat_number"] == "EG-100-001"
    # paid on the VAT-inclusive total
    resp = client.post(
        f"/api/invoices/{invoice['id']}/payments",
        json={"amount": 345.0, "method": "cash"},
        headers={**vat, "Idempotency-Key": f"pay-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["remaining"] == 0


def test_inclusive_vat_total_unchanged(client, clinic, vat):
    """Inclusive -> tax is split out, total stays equal to subtotal."""
    admin = vat
    _set_setting(client, admin, "billing.vat_inclusive", True)
    visit_id = _complete_visit(client, clinic)
    invoice = _invoice_visit(client, admin, visit_id)
    assert invoice["tax_rate"] == 15
    assert round(invoice["tax_total"], 2) == round(300 * 15 / 115, 2)
    assert round(invoice["total"], 2) == 300.0
    assert round(invoice["total"] - invoice["tax_total"], 2) == round(300 * 100 / 115, 2)


def test_vat_snapshot_immutable(client, clinic, vat):
    """Changing the rate after creation never touches existing invoices."""
    admin = vat
    visit_id = _complete_visit(client, clinic)
    invoice = _invoice_visit(client, admin, visit_id)
    assert invoice["tax_rate"] == 15
    _set_setting(client, admin, "billing.vat_rate_pct", 25)
    detail = client.get(f"/api/invoices/{invoice['id']}", headers=admin).json()
    assert detail["tax_rate"] == 15
    assert detail["total"] == 345.0


def test_exempt_clinic_no_tax(client, clinic, vat):
    admin = vat
    _set_setting(client, admin, "billing.vat_exempt", True)
    visit_id = _complete_visit(client, clinic)
    invoice = _invoice_visit(client, admin, visit_id)
    assert invoice["tax_rate"] == 0
    assert invoice["tax_total"] == 0
    assert invoice["total"] == 300.0
    assert invoice["vat_exempt"] is True


def test_discount_then_tax(client, clinic, vat):
    """Discount reduces the taxable base before VAT is applied."""
    admin = vat
    visit_id = _complete_visit(client, clinic)
    invoice = _invoice_visit(client, admin, visit_id)
    resp = client.post(
        f"/api/invoices/{invoice['id']}/discount",
        json={"kind": "fixed", "value": 100.0},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    detail = client.get(f"/api/invoices/{invoice['id']}", headers=admin).json()
    assert detail["discount_total"] == 100.0
    assert detail["taxable"] == 200.0
    assert detail["tax_total"] == 30.0
    assert detail["total"] == 230.0


def test_zero_rate_default_no_tax(client, clinic):
    """Out of the box (rate 0) invoices carry no tax and unchanged totals."""
    admin = admin_headers(client)
    visit_id = _complete_visit(client, clinic)
    invoice = _invoice_visit(client, admin, visit_id)
    assert invoice["tax_rate"] == 0
    assert invoice["tax_total"] == 0
    assert invoice["total"] == 300.0
