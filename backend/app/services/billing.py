"""Billing service (Plan/06 M2–M7): auto-invoice, discounts, payments,
refunds, immutability, numbering, row locks."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError
from app.models.billing import Discount, Invoice, InvoiceItem, Payment
from app.models.emr import Visit
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.scheduling import VisitType
from app.services.pricing import resolve_for_visit
from app.services.sequences import next_sequence

logger = logging.getLogger("hmsv2.billing")

PAYMENT_METHODS = ("cash", "card", "fawry", "instapay", "wallet", "meeza")


def _now() -> datetime:
    return datetime.now(UTC)


def _lock_invoice(db: Session, invoice_id: int) -> None:
    """Serializes payment/discount mutations per invoice (SQLite write-lock;
    Postgres FOR UPDATE)."""
    from app.models.identity import NumberSequence

    scope = f"invoice_lock:{invoice_id}"
    row = db.scalar(
        select(NumberSequence)
        .where(NumberSequence.scope == scope, NumberSequence.year.is_(None))
        .with_for_update()
    )
    if row is None:
        db.add(NumberSequence(scope=scope, year=None, value=0))
        db.flush()
    else:
        row.value += 1
        db.flush()


def next_invoice_number(db: Session) -> str:
    year = _now().year
    return f"INV-{year}-{next_sequence(db, 'invoice', year):06d}"


def create_invoice_from_visit(
    db: Session,
    audit_db: Session,
    *,
    visit: Visit,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Invoice:
    """Cashier flow (manual trigger): builds the invoice for a completed
    visit. Idempotent via the unique visit_id — a second call is a 409."""
    if visit.status != "completed":
        raise AppError("CONFLICT", "only completed visits can be invoiced")
    existing = db.scalar(select(Invoice).where(Invoice.visit_id == visit.id))
    if existing is not None:
        raise AppError("CONFLICT", "visit already invoiced")

    doctor = db.get(Doctor, visit.doctor_id)
    visit_type = db.get(VisitType, visit.visit_type_id)
    if doctor is None or visit_type is None:
        raise AppError("CONFLICT", "visit has no doctor or visit type")
    resolved = resolve_for_visit(db, visit, doctor, visit_type)

    from app.services.visits import visit_type_display_name

    description = visit_type_display_name(db, visit)
    profile = db.get(PatientProfile, visit.patient_profile_id)
    syndicate_id = profile.syndicate_id if profile else None

    subtotal = round(resolved.price, 2)
    invoice = Invoice(
        number=next_invoice_number(db),
        patient_profile_id=visit.patient_profile_id,
        visit_id=visit.id,
        appointment_id=visit.appointment_id,
        doctor_id=visit.doctor_id,
        syndicate_id=syndicate_id,
        subtotal=subtotal,
        discount_total=0,
        total=subtotal,
        patient_due=subtotal - (resolved.syndicate_coverage or 0),
        syndicate_due=resolved.syndicate_coverage or 0,
        currency="EGP",
        status="issued",
        issued_by=actor.id,
        issued_at=_now(),
        record_version=1,
    )
    db.add(invoice)
    db.flush()
    db.add(
        InvoiceItem(
            invoice_id=invoice.id,
            description=description,
            description_ar=visit_type.name_ar,
            qty=1,
            unit_price=subtotal,
            line_total=subtotal,
            visit_type_id=visit_type.id,
        )
    )
    try:
        with audit.audited_action(
            audit_db,
            actor_type="staff", actor_id=actor.id, actor_label=actor.email,
            action="invoice.create", correlation_id=correlation_id,
            entity_type="invoice", entity_id=str(invoice.id),
            after={"number": invoice.number, "total": float(invoice.total),
                   "patient_due": float(invoice.patient_due),
                   "syndicate_due": float(invoice.syndicate_due)},
            ip=ip,
        ):
            db.commit()
    except Exception:
        logger.exception("invoice audit failed for visit %s", visit.id)
        db.rollback()
        raise
    return invoice


def invoice_payload(db: Session, invoice: Invoice) -> dict:
    items = db.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id).order_by(InvoiceItem.id)
    ).all()
    discounts = db.scalars(
        select(Discount).where(Discount.invoice_id == invoice.id).order_by(Discount.id)
    ).all()
    payments = db.scalars(
        select(Payment).where(Payment.invoice_id == invoice.id).order_by(Payment.id)
    ).all()
    return {
        "id": invoice.id,
        "number": invoice.number,
        "patient_profile_id": invoice.patient_profile_id,
        "visit_id": invoice.visit_id,
        "doctor_id": invoice.doctor_id,
        "syndicate_id": invoice.syndicate_id,
        "subtotal": float(invoice.subtotal),
        "discount_total": float(invoice.discount_total),
        "total": float(invoice.total),
        "patient_due": float(invoice.patient_due),
        "syndicate_due": float(invoice.syndicate_due),
        "paid_total": float(invoice.paid_total),
        "refunded_total": float(invoice.refunded_total),
        "net_paid": round(float(invoice.paid_total) - float(invoice.refunded_total), 2),
        "remaining": round(
            float(invoice.patient_due)
            - (float(invoice.paid_total) - float(invoice.refunded_total)),
            2,
        ),
        "status": invoice.status,
        "record_version": invoice.record_version,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "reissue_of_id": invoice.reissue_of_id,
        "items": [
            {
                "id": i.id, "description": i.description, "description_ar": i.description_ar,
                "qty": float(i.qty), "unit_price": float(i.unit_price),
                    "line_total": float(i.line_total),
            }
            for i in items
        ],
        "discounts": [
            {"id": d.id, "kind": d.kind, "value": float(d.value), "reason": d.reason,
             "granted_by": d.granted_by}
            for d in discounts
        ],
        "payments": [
            {
                "id": p.id, "amount": float(p.amount), "method": p.method,
                "reference": p.reference, "paid_at": p.paid_at.isoformat(),
                "is_refund": p.is_refund,
            }
            for p in payments
        ],
    }


def _recompute(invoice: Invoice) -> None:
    invoice.total = round(float(invoice.subtotal) - float(invoice.discount_total), 2)
    invoice.patient_due = round(invoice.total - float(invoice.syndicate_due), 2)
    if invoice.patient_due < 0:
        invoice.patient_due = 0


def add_discount(
    db: Session,
    audit_db: Session,
    *,
    invoice: Invoice,
    kind: str,
    value: float,
    reason: str | None,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Invoice:
    if invoice.status not in ("issued", "partially_paid") or invoice.paid_total > 0:
        raise AppError("CONFLICT", "discounts require an unpaid invoice (M5)")
    if invoice.paid_total > 0:
        raise AppError("CONFLICT", "invoice already has payments; it is frozen")
    _lock_invoice(db, invoice.id)

    # role caps (M3)
    if actor.role == "secretary":
        from app.services.settings import get_setting

        cap = float(get_setting(db, "billing.discount_cap_secretary_pct", 10))
        if kind == "percent" and value > cap:
            raise AppError("FORBIDDEN", f"discount exceeds secretary cap of {cap}%")
        if kind == "fixed":
            percent_of_total = (value / float(invoice.total)) * 100 if invoice.total else 0
            if percent_of_total > cap:
                raise AppError("FORBIDDEN", "fixed discount exceeds secretary cap")
    elif actor.role == "doctor":
        from app.models.identity import Doctor as _Doctor

        doctor = db.scalar(select(_Doctor).where(_Doctor.staff_user_id == actor.id))
        if doctor is None or doctor.id != invoice.doctor_id:
            raise AppError("FORBIDDEN", "doctors may only discount their own invoices")

    discount_value = value
    if kind == "percent":
        discount_value = round(float(invoice.subtotal) * value / 100, 2)
    # never reduce syndicate_due; patient_due cannot go below zero
    if discount_value > float(invoice.patient_due):
        raise AppError("VALIDATION", "discount exceeds patient share")

    before = {"discount_total": float(invoice.discount_total),
        "patient_due": float(invoice.patient_due)}
    db.add(
        Discount(invoice_id=invoice.id, kind=kind, value=value, reason=reason, granted_by=actor.id)
    )
    invoice.discount_total = round(float(invoice.discount_total) + discount_value, 2)
    _recompute(invoice)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="invoice.discount", correlation_id=correlation_id,
        entity_type="invoice", entity_id=str(invoice.id),
        before=before, after={"discount_total": float(invoice.discount_total),
                              "patient_due": float(invoice.patient_due)},
        ip=ip,
    ):
        db.commit()
    return invoice


def add_payment(
    db: Session,
    audit_db: Session,
    *,
    invoice: Invoice,
    amount: float,
    method: str,
    reference: str | None,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Invoice:
    if invoice.status in ("cancelled", "refunded"):
        raise AppError("CONFLICT", f"cannot pay a {invoice.status} invoice")
    _lock_invoice(db, invoice.id)
    remaining = round(
        float(invoice.patient_due) - (float(invoice.paid_total) - float(invoice.refunded_total)), 2
    )
    if amount > remaining + 0.001:
        raise AppError("CONFLICT", f"overpayment: remaining is {remaining}")

    before = {"paid_total": float(invoice.paid_total), "status": invoice.status}
    db.add(
        Payment(
            invoice_id=invoice.id, amount=round(amount, 2), method=method,
            reference=reference, received_by=actor.id, paid_at=_now(), is_refund=False,
        )
    )
    invoice.paid_total = round(float(invoice.paid_total) + amount, 2)
    invoice.record_version += 1
    invoice.status = (
        "paid"
        if float(invoice.paid_total) >= float(invoice.patient_due) - 0.001
        else "partially_paid"
    )
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="payment.add", correlation_id=correlation_id,
        entity_type="invoice", entity_id=str(invoice.id),
        before=before,
        after={"paid_total": float(invoice.paid_total), "status": invoice.status, "amount": amount},
        ip=ip,
    ):
        db.commit()
    return invoice


def refund(
    db: Session,
    audit_db: Session,
    *,
    invoice: Invoice,
    amount: float | None,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Invoice:
    _lock_invoice(db, invoice.id)
    net_paid = round(float(invoice.paid_total) - float(invoice.refunded_total), 2)
    refund_amount = round(amount if amount is not None else net_paid, 2)
    if refund_amount <= 0:
        raise AppError("VALIDATION", "refund amount must be positive")
    if refund_amount > net_paid + 0.001:
        raise AppError("CONFLICT", f"refund exceeds net paid ({net_paid})")

    before = {"refunded_total": float(invoice.refunded_total), "status": invoice.status}
    db.add(
        Payment(
            invoice_id=invoice.id, amount=refund_amount, method="cash",
            received_by=actor.id, paid_at=_now(), is_refund=True,
        )
    )
    invoice.refunded_total = round(float(invoice.refunded_total) + refund_amount, 2)
    invoice.record_version += 1
    if float(invoice.refunded_total) >= float(invoice.paid_total) - 0.001:
        invoice.status = "refunded"
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="payment.refund", correlation_id=correlation_id,
        entity_type="invoice", entity_id=str(invoice.id),
        before=before,
        after={"refunded_total": float(invoice.refunded_total), "status": invoice.status},
        ip=ip,
    ):
        db.commit()
    return invoice


def adjust_item(
    db: Session,
    audit_db: Session,
    *,
    invoice: Invoice,
    item: InvoiceItem,
    unit_price: float | None,
    qty: float | None,
    description: str | None,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Invoice:
    """Cashier flexibility: edit an item's price/qty/description on an unpaid
    invoice. Admin always allowed; cashiers only when the admin setting
    `billing.cashier_can_adjust_pricing` is enabled."""
    if invoice.status in ("cancelled", "refunded") or invoice.paid_total > 0:
        raise AppError("CONFLICT", "invoice is frozen after payments (M5)")
    _lock_invoice(db, invoice.id)

    if actor.role != "admin":
        from app.services.settings import get_setting

        allowed = bool(get_setting(db, "billing.cashier_can_adjust_pricing", False))
        if not allowed:
            raise AppError(
                "FORBIDDEN",
                "price adjustment is disabled; ask an admin to enable it in Settings",
            )

    before = {
        "unit_price": float(item.unit_price),
        "qty": float(item.qty),
        "description": item.description,
        "subtotal": float(invoice.subtotal),
    }
    if unit_price is not None:
        if unit_price < 0:
            raise AppError("VALIDATION", "unit_price cannot be negative")
        item.unit_price = round(unit_price, 2)
    if qty is not None:
        if qty <= 0:
            raise AppError("VALIDATION", "qty must be positive")
        item.qty = round(qty, 2)
    if description is not None and description.strip():
        item.description = description.strip()[:300]
    item.line_total = round(float(item.qty) * float(item.unit_price), 2)

    # recompute totals (discount and syndicate due untouched)
    items = db.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    ).all()
    invoice.subtotal = round(sum(float(i.line_total) for i in items), 2)
    invoice.total = round(invoice.subtotal - float(invoice.discount_total), 2)
    invoice.patient_due = round(max(invoice.total - float(invoice.syndicate_due), 0), 2)

    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="invoice.item_adjust", correlation_id=correlation_id,
        entity_type="invoice_item", entity_id=str(item.id),
        before=before,
        after={
            "unit_price": float(item.unit_price),
            "qty": float(item.qty),
            "subtotal": float(invoice.subtotal),
            "patient_due": float(invoice.patient_due),
        },
        ip=ip,
    ):
        db.commit()
    return invoice


def cancel_and_reissue(
    db: Session,
    audit_db: Session,
    *,
    invoice: Invoice,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Invoice:
    """M5 admin flow: cancels the invoice and creates a fresh linked one."""
    before = {"status": invoice.status}
    invoice.status = "cancelled"
    new_invoice = Invoice(
        number=next_invoice_number(db),
        patient_profile_id=invoice.patient_profile_id,
        doctor_id=invoice.doctor_id,
        syndicate_id=invoice.syndicate_id,
        subtotal=invoice.subtotal,
        discount_total=0,
        total=invoice.total,
        patient_due=invoice.patient_due,
        syndicate_due=invoice.syndicate_due,
        currency=invoice.currency,
        status="issued",
        issued_by=actor.id,
        issued_at=_now(),
        record_version=1,
        reissue_of_id=invoice.id,
    )
    db.add(new_invoice)
    db.flush()
    items = db.scalars(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    ).all()
    for item in items:
        db.add(
            InvoiceItem(
                invoice_id=new_invoice.id, description=item.description,
                description_ar=item.description_ar, qty=item.qty,
                unit_price=item.unit_price, line_total=item.line_total,
                visit_type_id=item.visit_type_id,
            )
        )
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="invoice.cancel_reissue", correlation_id=correlation_id,
        entity_type="invoice", entity_id=str(invoice.id),
        before=before, after={"reissued_as": new_invoice.number, "old_status": "cancelled"},
        ip=ip,
    ):
        db.commit()
    return new_invoice
