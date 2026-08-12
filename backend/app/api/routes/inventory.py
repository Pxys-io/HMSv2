"""Inventory/pharmacy endpoints (Plan/14 E)."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.identity import StaffUser
from app.models.inventory import (
    Product,
    ProductCategory,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
)
from app.services import inventory as inv

router = APIRouter(prefix="/api/inventory", tags=["inventory"])
viewer = Annotated[StaffUser, Depends(require_perm("inventory.view"))]
editor = Annotated[StaffUser, Depends(require_perm("inventory.edit"))]
purchaser = Annotated[StaffUser, Depends(require_perm("inventory.purchase"))]
dispenser = Annotated[StaffUser, Depends(require_perm("inventory.dispense"))]


def _product_payload(db: Session, p: Product) -> dict:
    return {
        "id": p.id, "category_id": p.category_id, "medication_id": p.medication_id,
        "name": p.name, "name_ar": p.name_ar, "form": p.form, "strength": p.strength,
        "sku": p.sku, "barcode": p.barcode, "unit": p.unit,
        "price": float(p.price), "cost": float(p.cost),
        "reorder_level": float(p.reorder_level),
        "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
        "is_active": p.is_active, "stock": inv.stock_quantity(db, p.id),
    }


@router.get("/products")
def list_products(
    current: viewer, db: DbDep,
    low_stock: bool = Query(default=False),
    expiring_days: int | None = Query(default=None, ge=1, le=365),
    category_id: int | None = None,
):
    stmt = select(Product).where(Product.is_active.is_(True))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    products = list(db.scalars(stmt.order_by(Product.name)).all())
    payloads = [_product_payload(db, p) for p in products]
    if low_stock:
        payloads = [p for p in payloads if p["stock"] <= p["reorder_level"]]
    if expiring_days:
        horizon = date.today() + timedelta(days=expiring_days)
        payloads = [
            p for p in payloads
            if p["expiry_date"] and date.fromisoformat(p["expiry_date"]) <= horizon
        ]
    return {"items": payloads}


@router.post("/products")
def create_product(
    body: dict, current: editor, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    name = str(body.get("name", "")).strip()
    if not name:
        raise AppError("VALIDATION", "name is required")
    product = Product(
        category_id=body.get("category_id"),
        medication_id=body.get("medication_id"),
        name=name, name_ar=body.get("name_ar"), form=body.get("form"),
        strength=body.get("strength"), sku=body.get("sku"), barcode=body.get("barcode"),
        unit=body.get("unit", "unit"),
        price=float(body.get("price", 0) or 0),
        cost=float(body.get("cost", 0) or 0),
        reorder_level=float(body.get("reorder_level", 0) or 0),
        expiry_date=(
            date.fromisoformat(body["expiry_date"]) if body.get("expiry_date") else None
        ),
    )
    db.add(product)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="inventory.product.create", correlation_id=get_request_id(request),
        entity_type="product", entity_id="0", after={"name": name},
    ):
        db.commit()
    if float(body.get("opening_stock", 0) or 0) > 0:
        inv.adjust_stock(db, product_id=product.id, kind="opening",
                         qty=float(body["opening_stock"]), actor_id=current.id,
                         ref="opening balance")
        db.commit()
    return _product_payload(db, product)


@router.patch("/products/{product_id}")
def update_product(
    product_id: int, body: dict, current: editor, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    product = db.get(Product, product_id)
    if product is None:
        raise AppError("NOT_FOUND", "product not found")
    for field in ("name", "name_ar", "form", "strength", "sku", "barcode", "unit",
                  "category_id", "medication_id", "is_active", "expiry_date"):
        if field in body:
            setattr(product, field, body[field])
    for field in ("price", "cost", "reorder_level"):
        if field in body:
            setattr(product, field, float(body[field] or 0))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="inventory.product.update", correlation_id=get_request_id(request),
        entity_type="product", entity_id=str(product_id),
    ):
        db.commit()
    return _product_payload(db, product)


@router.get("/products/{product_id}/movements")
def product_movements(product_id: int, current: viewer, db: DbDep):
    if db.get(Product, product_id) is None:
        raise AppError("NOT_FOUND", "product not found")
    return {
        "items": [
            {"id": m.id, "kind": m.kind, "qty": float(m.qty),
             "balance_after": float(m.balance_after), "ref": m.ref,
             "created_by": m.created_by,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in inv.movements(db, product_id)
        ]
    }


@router.post("/products/{product_id}/stock")
def adjust_product_stock(
    product_id: int, body: dict, current: editor, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    kind = body.get("kind", "adjust")
    qty = float(body.get("qty", 0) or 0)
    if qty <= 0:
        raise AppError("VALIDATION", "qty must be positive")
    new_balance = inv.adjust_stock(db, product_id=product_id, kind=kind, qty=qty,
                                   actor_id=current.id, ref=body.get("ref"))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action=f"inventory.stock.{kind}", correlation_id=get_request_id(request),
        entity_type="product", entity_id=str(product_id),
        after={"qty": qty, "balance_after": new_balance},
    ):
        db.commit()
    return {"balance_after": new_balance}


@router.post("/dispense")
def dispense(
    body: dict, current: dispenser, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    """Dispense stock; resolves a medication_id to its linked product so the
    Rx prescriber can dispense directly."""
    qty = float(body.get("qty", 0) or 0)
    if qty <= 0:
        raise AppError("VALIDATION", "qty must be positive")
    product = None
    if body.get("product_id"):
        product = db.get(Product, body["product_id"])
    elif body.get("medication_id"):
        product = db.scalar(
            select(Product).where(Product.medication_id == body["medication_id"])
        )
    if product is None:
        raise AppError("NOT_FOUND", "product not found")
    new_balance = inv.dispense_product(db, product=product, qty=qty,
                                       actor_id=current.id, ref=body.get("ref"))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="inventory.dispense", correlation_id=get_request_id(request),
        entity_type="product", entity_id=str(product.id),
        after={"qty": qty, "balance_after": new_balance},
    ):
        db.commit()
    return {"product_id": product.id, "balance_after": new_balance}


# ------------------------------------------------------------- suppliers


@router.get("/suppliers")
def list_suppliers(current: viewer, db: DbDep):
    rows = db.scalars(select(Supplier).order_by(Supplier.name)).all()
    return {"items": [
        {"id": s.id, "name": s.name, "phone": s.phone, "notes": s.notes} for s in rows
    ]}


@router.post("/suppliers")
def create_supplier(body: dict, current: purchaser, db: DbDep):
    name = str(body.get("name", "")).strip()
    if not name:
        raise AppError("VALIDATION", "name is required")
    supplier = Supplier(name=name, phone=body.get("phone"), notes=body.get("notes"))
    db.add(supplier)
    db.commit()
    return {"id": supplier.id, "name": supplier.name, "phone": supplier.phone,
            "notes": supplier.notes}


@router.get("/categories")
def list_categories(current: viewer, db: DbDep):
    rows = db.scalars(select(ProductCategory).order_by(ProductCategory.name)).all()
    return {"items": [
        {"id": c.id, "name": c.name, "name_ar": c.name_ar} for c in rows
    ]}


@router.post("/categories")
def create_category(body: dict, current: editor, db: DbDep):
    name = str(body.get("name", "")).strip()
    if not name:
        raise AppError("VALIDATION", "name is required")
    category = ProductCategory(name=name, name_ar=body.get("name_ar"))
    db.add(category)
    db.commit()
    return {"id": category.id, "name": category.name, "name_ar": category.name_ar}


# ------------------------------------------------------------- purchase orders


def _po_payload(db: Session, po: PurchaseOrder) -> dict:
    return {
        "id": po.id, "po_number": po.po_number, "supplier_id": po.supplier_id,
        "status": po.status,
        "ordered_at": po.ordered_at.isoformat() if po.ordered_at else None,
        "received_at": po.received_at.isoformat() if po.received_at else None,
        "notes": po.notes, "created_by": po.created_by,
        "items": [
            {"id": i.id, "product_id": i.product_id, "qty": float(i.qty),
             "received_qty": float(i.received_qty), "unit_cost": float(i.unit_cost)}
            for i in po.items
        ],
    }


@router.get("/purchase-orders")
def list_pos(current: purchaser, db: DbDep, status: str | None = None):
    stmt = select(PurchaseOrder).order_by(PurchaseOrder.id.desc())
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
    rows = db.scalars(stmt).all()
    return {"items": [_po_payload(db, po) for po in rows]}


@router.post("/purchase-orders")
def create_po(
    body: dict, current: purchaser, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    items = body.get("items") or []
    if not items:
        raise AppError("VALIDATION", "at least one item is required")
    seq = db.scalar(select(PurchaseOrder).order_by(PurchaseOrder.id.desc()).limit(1))
    po_number = f"PO-{date.today().year}-{(seq.id + 1) if seq else 1:04d}"
    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=body.get("supplier_id"),
        status="ordered",
        ordered_at=date.today(),
        notes=body.get("notes"),
        created_by=current.id,
    )
    db.add(po)
    db.flush()
    for item in items:
        product = db.get(Product, item.get("product_id"))
        if product is None:
            raise AppError("NOT_FOUND", "unknown product in items")
        db.add(PurchaseOrderItem(
            po_id=po.id, product_id=product.id,
            qty=float(item.get("qty", 0) or 0),
            unit_cost=float(item.get("unit_cost", 0) or 0),
        ))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="inventory.po.create", correlation_id=get_request_id(request),
        entity_type="purchase_order", entity_id=str(po.id),
        after={"po_number": po_number},
    ):
        db.commit()
    return _po_payload(db, po)


@router.post("/purchase-orders/{po_id}/receive")
def receive_po_route(
    po_id: int, current: purchaser, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise AppError("NOT_FOUND", "purchase order not found")
    updated = inv.receive_po(db, po=po, actor_id=current.id)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="inventory.po.receive", correlation_id=get_request_id(request),
        entity_type="purchase_order", entity_id=str(po_id),
    ):
        db.commit()
    return _po_payload(db, updated)
