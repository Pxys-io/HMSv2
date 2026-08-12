"""Financial routes (Plan/06 §3): pricing matrix, syndicates + contract
prices, invoices, payments, discounts, refunds, reports."""

import csv
import io
import json
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_role
from app.core.errors import AppError
from app.core.pagination import paginate
from app.models.billing import (
    Invoice,
    InvoiceItem,
    Payment,
    PriceListItem,
    Syndicate,
    SyndicatePrice,
)
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.scheduling import VisitType
from app.schemas.financial import (
    DiscountIn,
    InvoiceItemIn,
    ManualInvoiceCreate,
    PaymentIn,
    PricingPut,
    RefundIn,
    SyndicateCreate,
    SyndicatePricePut,
    SyndicateUpdate,
)
from app.services import billing as billing_service
from app.services.idempotency import claim, complete, get_key_from_request
from app.services.settings import clinic_timezone

router = APIRouter(prefix="/api", tags=["financial"])
admin = Annotated[StaffUser, Depends(require_role("admin"))]
cashier = Annotated[StaffUser, Depends(require_role("admin", "secretary"))]
cashier_or_doctor = Annotated[StaffUser, Depends(require_role("admin", "secretary", "doctor"))]


def _replay(
    request: Request, response: Response, db: Session, actor: StaffUser, payload: dict
) -> bool:
    key = get_key_from_request(request)
    if not key:
        return False
    replay = claim(db, owner_type="staff", owner_id=actor.id, key=key, payload=payload)
    if replay:
        response.status_code = replay["status"]
        response.body = json.dumps(replay["body"], ensure_ascii=False).encode()
        response.headers["Content-Type"] = "application/json"
        return True
    return False


def _finish(request: Request, db: Session, actor: StaffUser, body: dict) -> None:
    key = get_key_from_request(request)
    if key:
        complete(db, owner_type="staff", owner_id=actor.id, key=key, status=200, body=body)


def _doctor_name(db: Session, doctor: Doctor | None) -> str | None:
    if doctor is None or doctor.staff_user_id is None:
        return None
    user = db.get(StaffUser, doctor.staff_user_id)
    return user.full_name if user else None


def _get_invoice(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise AppError("NOT_FOUND", "invoice not found")
    return invoice


# ------------------------------------------------------------------ pricing


@router.get("/pricing")
def get_pricing(current: admin, db: DbDep, doctor_id: int | None = Query(default=None)):
    stmt = select(PriceListItem).order_by(PriceListItem.visit_type_id, PriceListItem.doctor_id)
    if doctor_id is not None:
        stmt = stmt.where(
            (PriceListItem.doctor_id == doctor_id) | (PriceListItem.doctor_id.is_(None))
        )
    rows = db.scalars(stmt).all()
    return [
        {"id": r.id, "visit_type_id": r.visit_type_id, "doctor_id": r.doctor_id,
         "price": float(r.price)}
        for r in rows
    ]


@router.put("/pricing")
def put_pricing(
    body: PricingPut,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="pricing.replace", correlation_id=get_request_id(request),
        entity_type="pricing", entity_id="matrix",
        after={"rows": len(body.rows)},
        ip=request.client.host if request.client else None,
    ):
        for row in body.rows:
            existing = db.scalar(
                select(PriceListItem).where(
                    PriceListItem.visit_type_id == row.visit_type_id,
                    PriceListItem.doctor_id == row.doctor_id,
                )
            )
            if existing is None:
                db.add(PriceListItem(**row.model_dump()))
            else:
                existing.price = row.price
        db.commit()
    return {"updated": len(body.rows)}


# ---------------------------------------------------------------- syndicates


@router.get("/syndicates")
def list_syndicates(current: admin, db: DbDep):
    rows = db.scalars(select(Syndicate).order_by(Syndicate.name)).all()
    return [
        {"id": s.id, "name": s.name, "name_ar": s.name_ar, "code": s.code,
         "contact_phone": s.contact_phone, "contact_email": s.contact_email,
         "is_active": s.is_active}
        for s in rows
    ]


@router.post("/syndicates")
def create_syndicate(
    body: SyndicateCreate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if db.scalar(select(Syndicate).where(Syndicate.code == body.code)):
        raise AppError("CONFLICT", "syndicate code already exists")
    syndicate = Syndicate(**body.model_dump())
    db.add(syndicate)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="syndicate.create", correlation_id=get_request_id(request),
        entity_type="syndicate", entity_id=str(syndicate.id),
        after={"name": syndicate.name, "code": syndicate.code},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": syndicate.id, "name": syndicate.name}


@router.patch("/syndicates/{syndicate_id}")
def update_syndicate(
    syndicate_id: int,
    body: SyndicateUpdate,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    syndicate = db.get(Syndicate, syndicate_id)
    if syndicate is None:
        raise AppError("NOT_FOUND", "syndicate not found")
    before = {"name": syndicate.name, "is_active": syndicate.is_active}
    for field in body.model_fields_set:
        setattr(syndicate, field, getattr(body, field))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="syndicate.update", correlation_id=get_request_id(request),
        entity_type="syndicate", entity_id=str(syndicate_id),
        before=before, after={"name": syndicate.name},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": syndicate.id}


@router.get("/syndicates/{syndicate_id}/prices")
def get_syndicate_prices(syndicate_id: int, current: admin, db: DbDep):
    if db.get(Syndicate, syndicate_id) is None:
        raise AppError("NOT_FOUND", "syndicate not found")
    rows = db.scalars(
        select(SyndicatePrice).where(SyndicatePrice.syndicate_id == syndicate_id).order_by(
            SyndicatePrice.visit_type_id
        )
    ).all()
    return [
        {"id": r.id, "visit_type_id": r.visit_type_id, "doctor_id": r.doctor_id,
         "syndicate_coverage": float(r.syndicate_coverage), "patient_share": float(r.patient_share)}
        for r in rows
    ]


@router.put("/syndicates/{syndicate_id}/prices")
def put_syndicate_prices(
    syndicate_id: int,
    body: SyndicatePricePut,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if db.get(Syndicate, syndicate_id) is None:
        raise AppError("NOT_FOUND", "syndicate not found")
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="syndicate.prices_replace", correlation_id=get_request_id(request),
        entity_type="syndicate", entity_id=str(syndicate_id),
        after={"rows": len(body.items)},
        ip=request.client.host if request.client else None,
    ):
        for item in body.items:
            existing = db.scalar(
                select(SyndicatePrice).where(
                    SyndicatePrice.syndicate_id == syndicate_id,
                    SyndicatePrice.visit_type_id == item.visit_type_id,
                    SyndicatePrice.doctor_id == item.doctor_id,
                )
            )
            if existing is None:
                db.add(SyndicatePrice(syndicate_id=syndicate_id, **item.model_dump()))
            else:
                existing.syndicate_coverage = item.syndicate_coverage
                existing.patient_share = item.patient_share
        db.commit()
    return {"updated": len(body.items)}


# ------------------------------------------------------------------ invoices


@router.get("/cashier/uninvoiced")
def uninvoiced_visits(current: cashier_or_doctor, db: DbDep):
    """Completed visits without an invoice — the cashier decides what to bill
    and creates the invoice manually (no auto-invoicing)."""
    from app.models.emr import Visit as _Visit
    from app.models.identity import Doctor as _Doctor
    from app.models.identity import PatientProfile as _Profile
    from app.services.pricing import resolve_for_visit

    rows = db.scalars(
        select(_Visit)
        .where(
            _Visit.status == "completed",
            ~_Visit.id.in_(select(Invoice.visit_id).where(Invoice.visit_id.isnot(None))),
        )
        .order_by(_Visit.ended_at.desc())
        .limit(50)
    ).all()
    out = []
    for visit in rows:
        profile = db.get(_Profile, visit.patient_profile_id)
        doctor = db.get(_Doctor, visit.doctor_id)
        visit_type = db.get(VisitType, visit.visit_type_id)
        price = None
        try:
            price = resolve_for_visit(db, visit, doctor, visit_type).price
        except Exception:  # noqa: BLE001 - per-hour visits without timings
            price = None
        from app.services.visits import visit_type_display_name

        out.append(
            {
                "visit_id": visit.id,
                "patient_profile_id": visit.patient_profile_id,
                "patient_name": profile.full_name if profile else None,
                "patient_phone": profile.phone if profile else None,
                "doctor_id": visit.doctor_id,
                "doctor_name": _doctor_name(db, doctor),
                "visit_type_id": visit.visit_type_id,
                "type_name": visit_type_display_name(db, visit),
                "custom_type_name": visit.custom_type_name,
                "ended_at": visit.ended_at.isoformat() if visit.ended_at else None,
                "price_preview": round(price, 2) if price is not None else None,
            }
        )
    return out


@router.post("/invoices/from-visit/{visit_id}")
def invoice_from_visit(
    visit_id: int,
    current: cashier,
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    """Secretary/admin bills a completed visit — the only way invoices are
    created for visits now."""
    if _replay(request, response, db, current, {"visit_id": visit_id}):
        return response
    from app.models.emr import Visit as _Visit
    from app.services.billing import create_invoice_from_visit

    visit = db.get(_Visit, visit_id)
    if visit is None:
        raise AppError("NOT_FOUND", "visit not found")
    invoice = create_invoice_from_visit(
        db, audit_db, visit=visit, actor=current,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    payload = billing_service.invoice_payload(db, invoice)
    _finish(request, db, current, payload)
    return payload


@router.get("/invoices")
def list_invoices(
    current: cashier_or_doctor,
    db: DbDep,
    status: str | None = Query(default=None),
    doctor_id: int | None = Query(default=None),
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(Invoice).order_by(Invoice.id.desc())
    if current.role == "doctor":
        doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == current.id))
        if doctor is None:
            raise AppError("FORBIDDEN", "no doctor profile")
        stmt = stmt.where(Invoice.doctor_id == doctor.id)
    if status is not None:
        stmt = stmt.where(Invoice.status == status)
    if doctor_id is not None:
        stmt = stmt.where(Invoice.doctor_id == doctor_id)
    if from_date is not None:
        stmt = stmt.where(Invoice.issued_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date is not None:
        stmt = stmt.where(Invoice.issued_at <= datetime.combine(to_date, datetime.max.time()))
    result = paginate(db, stmt, page, page_size)
    result["items"] = [billing_service.invoice_payload(db, i) for i in result["items"]]
    return result


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, current: cashier_or_doctor, db: DbDep):
    invoice = _get_invoice(db, invoice_id)
    if current.role == "doctor":
        doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == current.id))
        if doctor is None or doctor.id != invoice.doctor_id:
            raise AppError("FORBIDDEN", "not your invoice")
    return billing_service.invoice_payload(db, invoice)


@router.post("/invoices/manual")
def create_manual_invoice(
    body: ManualInvoiceCreate,
    current: cashier,
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay(request, response, db, current, body.model_dump(mode="json")):
        return response
    if db.get(PatientProfile, body.patient_profile_id) is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    if db.get(Doctor, body.doctor_id) is None:
        raise AppError("NOT_FOUND", "doctor not found")
    if body.syndicate_id is not None and db.get(Syndicate, body.syndicate_id) is None:
        raise AppError("NOT_FOUND", "syndicate not found")
    subtotal = round(sum(i.qty * i.unit_price for i in body.items), 2)
    invoice = Invoice(
        number=billing_service.next_invoice_number(db),
        patient_profile_id=body.patient_profile_id,
        doctor_id=body.doctor_id,
        syndicate_id=body.syndicate_id,
        subtotal=subtotal,
        discount_total=0,
        total=subtotal,
        patient_due=subtotal,
        syndicate_due=0,
        currency="EGP",
        status="issued",
        issued_by=current.id,
        issued_at=datetime.now(clinic_timezone()),
        record_version=1,
    )
    db.add(invoice)
    db.flush()
    for item in body.items:
        db.add(
            InvoiceItem(
                invoice_id=invoice.id, description=item.description,
                description_ar=item.description_ar, qty=item.qty,
                unit_price=item.unit_price, line_total=round(item.qty * item.unit_price, 2),
            )
        )
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="invoice.manual", correlation_id=get_request_id(request),
        entity_type="invoice", entity_id=str(invoice.id),
        after={"number": invoice.number, "total": float(invoice.total)},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    payload = billing_service.invoice_payload(db, invoice)
    _finish(request, db, current, payload)
    return payload


@router.post("/invoices/{invoice_id}/items")
def add_invoice_item(
    invoice_id: int,
    body: InvoiceItemIn,
    current: cashier,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    invoice = _get_invoice(db, invoice_id)
    if invoice.paid_total > 0 or invoice.status not in ("issued", "partially_paid"):
        raise AppError("CONFLICT", "invoice is frozen after payments (M5)")
    before = {"subtotal": float(invoice.subtotal), "total": float(invoice.total)}
    db.add(
        InvoiceItem(
            invoice_id=invoice.id, description=body.description,
            description_ar=body.description_ar, qty=body.qty,
            unit_price=body.unit_price, line_total=round(body.qty * body.unit_price, 2),
        )
    )
    invoice.subtotal = round(float(invoice.subtotal) + body.qty * body.unit_price, 2)
    billing_service._recompute(invoice)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="invoice.item_add", correlation_id=get_request_id(request),
        entity_type="invoice", entity_id=str(invoice_id),
        before=before, after={"subtotal": float(invoice.subtotal)},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return billing_service.invoice_payload(db, invoice)


@router.post("/invoices/{invoice_id}/discount")
def add_discount(
    invoice_id: int,
    body: DiscountIn,
    current: cashier_or_doctor,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    invoice = _get_invoice(db, invoice_id)
    updated = billing_service.add_discount(
        db, audit_db, invoice=invoice, kind=body.kind, value=body.value,
        reason=body.reason, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return billing_service.invoice_payload(db, updated)


@router.post("/invoices/{invoice_id}/payments")
def add_payment(
    invoice_id: int,
    body: PaymentIn,
    current: cashier,
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _replay(request, response, db, current, {"invoice_id": invoice_id, **body.model_dump()}):
        return response
    invoice = _get_invoice(db, invoice_id)
    updated = billing_service.add_payment(
        db, audit_db, invoice=invoice, amount=body.amount, method=body.method,
        reference=body.reference, actor=current, correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    payload = billing_service.invoice_payload(db, updated)
    _finish(request, db, current, payload)
    return payload


@router.post("/payments/{payment_id}/refund")
def refund_payment(
    payment_id: int,
    body: RefundIn,
    current: admin,
    request: Request,
    response: Response,
    db: DbDep,
    audit_db: AuditDbDep,
):
    payment = db.get(Payment, payment_id)
    if payment is None or payment.is_refund:
        raise AppError("NOT_FOUND", "payment not found")
    if _replay(request, response, db, current, {"payment_id": payment_id, **body.model_dump()}):
        return response
    invoice = _get_invoice(db, payment.invoice_id)
    updated = billing_service.refund(
        db, audit_db, invoice=invoice, amount=body.amount, actor=current,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    payload = billing_service.invoice_payload(db, updated)
    _finish(request, db, current, payload)
    return payload


@router.post("/invoices/{invoice_id}/cancel-reissue")
def cancel_reissue(
    invoice_id: int,
    current: admin,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    invoice = _get_invoice(db, invoice_id)
    new_invoice = billing_service.cancel_and_reissue(
        db, audit_db, invoice=invoice, actor=current,
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return {
        "cancelled": invoice.number,
        "reissued": new_invoice.number,
        "new_invoice_id": new_invoice.id,
    }


# ------------------------------------------------------------------ reports


def _clinic_day(dt: datetime) -> date:
    return dt.astimezone(clinic_timezone()).date()


@router.get("/reports/daily-revenue")
def daily_revenue(
    current: admin,
    db: DbDep,
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    format: str = "json",
):
    payments = db.scalars(
        select(Payment).where(Payment.paid_at >= datetime.combine(from_date, datetime.min.time()),
                              Payment.paid_at <= datetime.combine(to_date, datetime.max.time()))
    ).all()
    buckets: dict[tuple[date, str], float] = {}
    for p in payments:
        key = (_clinic_day(p.paid_at), p.method)
        amount = -float(p.amount) if p.is_refund else float(p.amount)
        buckets[key] = round(buckets.get(key, 0) + amount, 2)
    rows = [
        {"date": day.isoformat(), "method": method, "net": net}
        for (day, method), net in sorted(buckets.items())
    ]
    if format == "csv":
        return _csv_response(rows, ["date", "method", "net"])
    return {"from": from_date.isoformat(), "to": to_date.isoformat(), "rows": rows}


@router.get("/reports/doctor-share")
def doctor_share(
    current: admin,
    db: DbDep,
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
    format: str = "json",
):
    invoices = db.scalars(
        select(Invoice).where(
            Invoice.issued_at >= datetime.combine(from_date, datetime.min.time()),
            Invoice.issued_at <= datetime.combine(to_date, datetime.max.time()),
            Invoice.status != "cancelled",
        )
    ).all()
    rows: list[dict] = []
    by_doctor: dict[int, dict] = {}
    for inv in invoices:
        bucket = by_doctor.setdefault(
            inv.doctor_id,
            {"doctor_id": inv.doctor_id, "doctor_name": None, "visits": 0,
             "invoiced": 0.0, "collected": 0.0},
        )
        bucket["visits"] += 1 if inv.visit_id else 0
        bucket["invoiced"] = round(bucket["invoiced"] + float(inv.total), 2)
        bucket["collected"] = round(
            bucket["collected"] + float(inv.paid_total) - float(inv.refunded_total), 2
        )
    for doctor_id, bucket in by_doctor.items():
        doctor = db.get(Doctor, doctor_id)
        if doctor:
            user = db.get(StaffUser, doctor.staff_user_id)
            bucket["doctor_name"] = user.full_name if user else None
        rows.append(bucket)
    rows.sort(key=lambda r: r["doctor_id"])
    if format == "csv":
        return _csv_response(rows, ["doctor_id", "doctor_name", "visits", "invoiced", "collected"])
    return {"from": from_date.isoformat(), "to": to_date.isoformat(), "rows": rows}


@router.get("/reports/syndicate-balances")
def syndicate_balances(current: admin, db: DbDep, format: str = "json"):
    syndicates = db.scalars(select(Syndicate).order_by(Syndicate.name)).all()
    rows = []
    for syndicate in syndicates:
        invoices = db.scalars(
            select(Invoice).where(
                Invoice.syndicate_id == syndicate.id, Invoice.status != "cancelled"
            )
        ).all()
        balance = round(sum(float(i.syndicate_due) for i in invoices), 2)
        rows.append(
            {"syndicate_id": syndicate.id, "name": syndicate.name,
             "accrued_balance": balance, "invoices": len(invoices)}
        )
    if format == "csv":
        return _csv_response(rows, ["syndicate_id", "name", "accrued_balance", "invoices"])
    return {"rows": rows}


def _csv_response(rows: list[dict], columns: list[str]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return Response(
        content=buffer.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )
