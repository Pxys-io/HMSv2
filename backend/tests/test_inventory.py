"""Inventory tests (Plan/14 E done-when: 3 products, PO, receive, dispense,
low-stock)."""

import secrets

from tests.test_financial import admin_headers


def _product(client, admin, name, cost=10, price=25, opening=100, reorder=20):
    resp = client.post(
        "/api/inventory/products",
        json={"name": name, "cost": cost, "price": price, "opening_stock": opening,
              "reorder_level": reorder, "unit": "box"},
        headers={**admin, "Idempotency-Key": f"pr-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_inventory_flow_done_when(client):
    """create products -> PO -> receive -> stock moves -> dispense -> low stock."""
    admin = admin_headers(client)
    p1 = _product(client, admin, "Amoxicillin 500", cost=12, opening=50, reorder=10)
    _product(client, admin, "Paracetamol 500", cost=3, opening=30, reorder=10)
    p3 = _product(client, admin, "Omeprazole 20", cost=8, opening=5, reorder=20)
    assert p1["stock"] == 50.0
    assert p1["cost"] == 12.0

    # low-stock: p3 (5 <= 20) shows in low_stock list; p1/p2 don't
    low = client.get("/api/inventory/products?low_stock=true", headers=admin).json()["items"]
    ids = {p["id"] for p in low}
    assert p3["id"] in ids
    assert p1["id"] not in ids

    # purchase order for p1
    po = client.post(
        "/api/inventory/purchase-orders",
        json={"items": [{"product_id": p1["id"], "qty": 100, "unit_cost": 11}]},
        headers={**admin, "Idempotency-Key": f"po-{secrets.token_hex(4)}"},
    ).json()
    assert po["status"] == "ordered"
    assert po["items"][0]["qty"] == 100.0

    # receive -> stock moves
    client.post(f"/api/inventory/purchase-orders/{po['id']}/receive", headers=admin)
    detail = client.get(
        f"/api/inventory/products/{p1['id']}/movements", headers=admin
    ).json()["items"]
    kinds = [m["kind"] for m in detail]
    assert "opening" in kinds and "in" in kinds
    po2 = client.get("/api/inventory/purchase-orders", headers=admin).json()["items"][0]
    assert po2["status"] == "received"
    low = client.get("/api/inventory/products?low_stock=true", headers=admin).json()["items"]
    assert p1["id"] not in {p["id"] for p in low}  # 150 > 10 now

    # dispense 30 of p1 -> 120 on hand
    resp = client.post(
        "/api/inventory/dispense",
        json={"product_id": p1["id"], "qty": 30, "ref": "rx-1234"},
        headers={**admin, "Idempotency-Key": f"ds-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance_after"] == 120.0

    # over-dispense rejected
    resp = client.post("/api/inventory/dispense",
                       json={"product_id": p3["id"], "qty": 999}, headers=admin)
    assert resp.status_code == 422


def test_dispense_from_prescription_medication(client):
    admin = admin_headers(client)
    # create a product linked to a medication, dispense by medication_id
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.emr import Medication

    db = SessionLocal()
    med = db.scalar(select(Medication).limit(1))
    if med is None:
        med = Medication(name="TestMed", name_ar="تست", form="tab", strength="10mg")
        db.add(med)
        db.commit()
    med_id = med.id
    db.close()
    _product(client, admin, "TestMed 10", opening=40, reorder=5)
    # link the medication to the product
    products = client.get("/api/inventory/products", headers=admin).json()["items"]
    product = next(p for p in products if p["name"] == "TestMed 10")
    client.patch(f"/api/inventory/products/{product['id']}",
                 json={"medication_id": med_id}, headers=admin)
    resp = client.post(
        "/api/inventory/dispense",
        json={"medication_id": med_id, "qty": 5, "ref": "rx-99"},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance_after"] == 35.0
