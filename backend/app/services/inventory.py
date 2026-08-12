"""Inventory service (Plan/14 E): stock ledger, purchase orders, dispensing."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.inventory import (
    Product,
    PurchaseOrder,
    StockLevel,
    StockMovement,
)


def stock_quantity(db: Session, product_id: int) -> float:
    level = db.get(StockLevel, product_id)
    return float(level.quantity) if level else 0.0


def ensure_level(db: Session, product_id: int) -> StockLevel:
    level = db.get(StockLevel, product_id)
    if level is None:
        level = StockLevel(product_id=product_id, quantity=0)
        db.add(level)
        db.flush()
    return level


def _move(
    db: Session,
    *,
    product_id: int,
    kind: str,
    qty: float,
    actor_id: int | None,
    ref: str | None = None,
) -> float:
    """Applies a ledger movement and returns the new balance."""
    if qty < 0:
        raise AppError("VALIDATION", "qty must be positive")
    level = ensure_level(db, product_id)
    delta = qty if kind in ("in", "opening") else -qty
    new_balance = round(float(level.quantity) + delta, 2)
    if new_balance < 0:
        raise AppError("VALIDATION", f"insufficient stock (on hand: {level.quantity:.2f})")
    level.quantity = new_balance
    db.add(
        StockMovement(
            product_id=product_id, kind=kind, qty=qty, balance_after=new_balance,
            ref=ref, created_by=actor_id,
        )
    )
    return new_balance


def adjust_stock(
    db: Session, *, product_id: int, kind: str, qty: float,
    actor_id: int | None, ref: str | None = None,
) -> float:
    if kind not in ("in", "out", "adjust", "opening"):
        raise AppError("VALIDATION", "kind must be in/out/adjust/opening")
    if db.get(Product, product_id) is None:
        raise AppError("NOT_FOUND", "product not found")
    return _move(db, product_id=product_id, kind=kind, qty=qty, actor_id=actor_id, ref=ref)


def receive_po(db: Session, *, po: PurchaseOrder, actor_id: int) -> PurchaseOrder:
    """Receives the whole PO: stock in, movement logged, status -> received."""
    if po.status == "received":
        raise AppError("CONFLICT", "purchase order already received")
    for item in po.items:
        pending = float(item.qty) - float(item.received_qty)
        if pending > 0:
            _move(db, product_id=item.product_id, kind="in", qty=pending,
                  actor_id=actor_id, ref=f"PO {po.po_number}")
            item.received_qty = float(item.received_qty) + pending
    po.status = "received"
    po.received_at = date.today()
    return po


def dispense_product(
    db: Session, *, product: Product, qty: float, actor_id: int | None,
    ref: str | None = None,
) -> float:
    """Dispensing (e.g., from a prescription) decrements stock."""
    return _move(db, product_id=product.id, kind="out", qty=qty, actor_id=actor_id, ref=ref)


def movements(db: Session, product_id: int, limit: int = 100) -> list[StockMovement]:
    return list(
        db.scalars(
            select(StockMovement).where(StockMovement.product_id == product_id)
            .order_by(StockMovement.id.desc()).limit(limit)
        ).all()
    )
