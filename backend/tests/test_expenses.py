"""Expenses + petty cash + P&L tests (Plan/14 B)."""

import secrets
from datetime import date

import pytest

from app.db.session import SessionLocal
from tests.test_financial import _complete_visit, _invoice_visit, admin_headers

TODAY = date.today()


@pytest.fixture(autouse=True)
def _clean_expenses():
    """The session DB is shared; wipe expense/petty-cash state per test."""
    db = SessionLocal()
    from sqlalchemy import delete

    from app.models.expense import Expense, PettyCashTransaction

    db.execute(delete(PettyCashTransaction))
    db.execute(delete(Expense))
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.execute(delete(PettyCashTransaction))
    db.execute(delete(Expense))
    db.commit()
    db.close()


def _expense_headers(client):
    return admin_headers(client)


def test_expense_drops_petty_cash(client, clinic):
    """B done-when (part 1): expense entered -> petty cash balance drops."""
    admin = _expense_headers(client)
    client.put("/api/settings", json={"petty_cash.opening_balance": 1000}, headers=admin)
    balance = client.get("/api/petty-cash/balance", headers=admin).json()
    assert balance["balance"] == 1000.0

    resp = client.post(
        "/api/expenses",
        json={"category": "office", "amount": 250, "expense_date": TODAY.isoformat(),
              "note": "printer paper"},
        headers={**admin, "Idempotency-Key": f"ex-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    balance = client.get("/api/petty-cash/balance", headers=admin).json()
    assert balance["balance"] == 750.0
    assert balance["transactions"][0]["kind"] == "out"
    assert balance["transactions"][0]["amount"] == 250.0


def test_expense_over_balance_rejected(client, clinic):
    admin = _expense_headers(client)
    client.put("/api/settings", json={"petty_cash.opening_balance": 100}, headers=admin)
    resp = client.post(
        "/api/expenses",
        json={"category": "medical", "amount": 500, "expense_date": TODAY.isoformat()},
        headers=admin,
    )
    assert resp.status_code == 422


def test_bank_expense_does_not_touch_petty_cash(client, clinic):
    admin = _expense_headers(client)
    client.put("/api/settings", json={"petty_cash.opening_balance": 500}, headers=admin)
    resp = client.post(
        "/api/expenses",
        json={"category": "rent", "amount": 300, "expense_date": TODAY.isoformat(),
              "paid_from": "bank"},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    balance = client.get("/api/petty-cash/balance", headers=admin).json()
    assert balance["balance"] == 500.0


def test_petty_cash_in_out(client, clinic):
    admin = _expense_headers(client)
    client.put("/api/settings", json={"petty_cash.opening_balance": 0}, headers=admin)
    client.post("/api/petty-cash/in", json={"amount": 200, "note": "top up"},
                headers={**admin, "Idempotency-Key": f"in-{secrets.token_hex(4)}"})
    assert client.get("/api/petty-cash/balance", headers=admin).json()["balance"] == 200.0
    client.post("/api/petty-cash/out", json={"amount": 80, "note": "coffee"},
                headers={**admin, "Idempotency-Key": f"out-{secrets.token_hex(4)}"})
    balance = client.get("/api/petty-cash/balance", headers=admin).json()
    assert balance["balance"] == 120.0
    # overdraft rejected
    resp = client.post("/api/petty-cash/out", json={"amount": 500, "note": "nope"}, headers=admin)
    assert resp.status_code == 422


def test_expense_delete_reverses(client, clinic):
    admin = _expense_headers(client)
    client.put("/api/settings", json={"petty_cash.opening_balance": 1000}, headers=admin)
    created = client.post(
        "/api/expenses",
        json={"category": "office", "amount": 200, "expense_date": TODAY.isoformat()},
        headers=admin,
    ).json()
    assert client.get("/api/petty-cash/balance", headers=admin).json()["balance"] == 800.0
    client.delete(f"/api/expenses/{created['id']}", headers=admin)
    assert client.get("/api/petty-cash/balance", headers=admin).json()["balance"] == 1000.0
    items = client.get("/api/expenses", headers=admin).json()["items"]
    assert all(i["id"] != created["id"] for i in items)


def test_monthly_pnl(client, clinic):
    """B done-when (part 2): P&L moves by revenue - refunds - expenses."""
    admin = admin_headers(client)
    month = TODAY.strftime("%Y-%m")
    baseline = client.get(f"/api/pnl?month={month}", headers=admin).json()
    visit_id = _complete_visit(client, clinic)
    invoice = _invoice_visit(client, admin, visit_id)
    client.post(
        f"/api/invoices/{invoice['id']}/payments",
        json={"amount": 300.0, "method": "cash"},
        headers={**admin, "Idempotency-Key": f"pay-{secrets.token_hex(4)}"},
    )
    client.put("/api/settings", json={"petty_cash.opening_balance": 500}, headers=admin)
    resp = client.post(
        "/api/expenses",
        json={"category": "medical", "amount": 50, "expense_date": TODAY.isoformat()},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    pnl = client.get(f"/api/pnl?month={month}", headers=admin).json()
    assert pnl["revenue"] - baseline["revenue"] == 300.0
    assert pnl["refunds"] - baseline["refunds"] == 0
    assert pnl["expenses"] - baseline["expenses"] == 50.0
    assert pnl["net"] - baseline["net"] == 250.0

    # a refund in the same month reduces revenue
    inv = client.get(f"/api/invoices/{invoice['id']}", headers=admin).json()
    payment = inv["payments"][0]
    client.post(
        f"/api/payments/{payment['id']}/refund",
        json={"amount": 100.0, "method": "cash"},
        headers=admin,
    )
    pnl = client.get(f"/api/pnl?month={month}", headers=admin).json()
    assert pnl["refunds"] - baseline["refunds"] == 100.0
    assert pnl["net"] - baseline["net"] == 150.0


def test_bad_month_rejected(client, clinic):
    admin = admin_headers(client)
    resp = client.get("/api/pnl?month=2026-13", headers=admin)
    assert resp.status_code == 422
