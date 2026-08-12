"""Referral + lab-order endpoints (Plan/14 C6, C7)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.identity import PatientProfile, StaffUser
from app.models.ops import LabOrder, Referral
from app.services.activity import log_activity

router = APIRouter(prefix="/api", tags=["ops"])
user = Annotated[StaffUser, Depends(require_perm("ops.referral"))]


def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _referral_payload(r: Referral) -> dict:
    return {
        "id": r.id, "patient_profile_id": r.patient_profile_id,
        "from_doctor_id": r.from_doctor_id, "to_text": r.to_text, "place": r.place,
        "notes": r.notes, "referral_date": _iso(r.referral_date), "status": r.status,
        "outcome_seen_at": _iso(r.outcome_seen_at), "outcome_text": r.outcome_text,
        "outcome_updated_by": r.outcome_updated_by,
        "created_at": _iso(r.created_at),
    }


def _lab_payload(order: LabOrder) -> dict:
    return {
        "id": order.id, "patient_profile_id": order.patient_profile_id,
        "doctor_id": order.doctor_id, "lab_name": order.lab_name, "tests": order.tests,
        "order_date": _iso(order.order_date), "status": order.status,
        "notes": order.notes, "results_attachment_id": order.results_attachment_id,
        "created_at": _iso(order.created_at),
    }


# ------------------------------------------------------------- referrals


@router.get("/referrals")
def list_referrals(
    current: user, db: DbDep,
    status: str | None = Query(default=None),
    patient_id: int | None = Query(default=None),
):
    stmt = select(Referral).where(Referral.is_deleted.is_(False))
    if status:
        stmt = stmt.where(Referral.status == status)
    if patient_id:
        stmt = stmt.where(Referral.patient_profile_id == patient_id)
    rows = db.scalars(stmt.order_by(Referral.referral_date.desc(), Referral.id.desc())).all()
    return {"items": [_referral_payload(r) for r in rows]}


@router.post("/referrals")
def create_referral(
    body: dict, current: user, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    to_text = str(body.get("to_text", "")).strip()
    if not to_text:
        raise AppError("VALIDATION", "to_text is required")
    pid = body.get("patient_profile_id")
    if not pid or not db.get(PatientProfile, pid):
        raise AppError("VALIDATION", "patient_profile_id is required")
    referral = Referral(
        patient_profile_id=body["patient_profile_id"],
        from_doctor_id=body.get("from_doctor_id") or current.id,
        to_text=to_text,
        place=body.get("place"),
        notes=body.get("notes"),
        referral_date=date.fromisoformat(str(body.get("referral_date", date.today().isoformat()))),
        status="pending",
    )
    db.add(referral)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="referral.create", correlation_id=get_request_id(request),
        entity_type="referral", entity_id="0", after={"to_text": to_text},
    ):
        db.commit()
    log_activity(db, patient_profile_id=referral.patient_profile_id, type="referral.created",
                 actor_id=current.id, actor_label=current.email, referral_id=referral.id)
    return _referral_payload(referral)


@router.patch("/referrals/{referral_id}")
def update_referral(
    referral_id: int, body: dict, current: user, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    referral = db.get(Referral, referral_id)
    if referral is None or referral.is_deleted:
        raise AppError("NOT_FOUND", "referral not found")
    for field in ("to_text", "place", "notes", "status"):
        if field in body:
            setattr(referral, field, body[field])
    if "outcome" in body or "outcome_seen_at" in body:
        referral.outcome_text = body.get("outcome", body.get("outcome_text"))
        referral.outcome_seen_at = (
            date.fromisoformat(str(body["outcome_seen_at"]))
            if body.get("outcome_seen_at")
            else None
        )
        referral.outcome_updated_by = current.id
        if body.get("status") is None:
            referral.status = "seen"
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="referral.update", correlation_id=get_request_id(request),
        entity_type="referral", entity_id=str(referral_id),
    ):
        db.commit()
    return _referral_payload(referral)


@router.delete("/referrals/{referral_id}")
def delete_referral(
    referral_id: int, current: user, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    referral = db.get(Referral, referral_id)
    if referral is None or referral.is_deleted:
        raise AppError("NOT_FOUND", "referral not found")
    referral.is_deleted = True
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="referral.delete", correlation_id=get_request_id(request),
        entity_type="referral", entity_id=str(referral_id),
    ):
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------- lab orders


@router.get("/lab-orders")
def list_lab_orders(
    current: user, db: DbDep,
    status: str | None = Query(default=None),
    patient_id: int | None = Query(default=None),
):
    stmt = select(LabOrder).where(LabOrder.is_deleted.is_(False))
    if status:
        stmt = stmt.where(LabOrder.status == status)
    if patient_id:
        stmt = stmt.where(LabOrder.patient_profile_id == patient_id)
    rows = db.scalars(stmt.order_by(LabOrder.order_date.desc(), LabOrder.id.desc())).all()
    return {"items": [_lab_payload(o) for o in rows]}


@router.post("/lab-orders")
def create_lab_order(
    body: dict, current: user, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    lab_name = str(body.get("lab_name", "")).strip()
    if not lab_name:
        raise AppError("VALIDATION", "lab_name is required")
    tests = body.get("tests") or []
    if not isinstance(tests, list) or not tests:
        raise AppError("VALIDATION", "tests must be a non-empty list")
    order = LabOrder(
        patient_profile_id=body.get("patient_profile_id"),
        doctor_id=body.get("doctor_id") or current.id,
        lab_name=lab_name,
        tests=tests,
        order_date=date.fromisoformat(str(body.get("order_date", date.today().isoformat()))),
        status="pending",
        notes=body.get("notes"),
    )
    pid = body.get("patient_profile_id")
    if not pid or not db.get(PatientProfile, pid):
        raise AppError("VALIDATION", "patient_profile_id is required")
    db.add(order)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="lab_order.create", correlation_id=get_request_id(request),
        entity_type="lab_order", entity_id="0", after={"lab_name": lab_name},
    ):
        db.commit()
    log_activity(db, patient_profile_id=order.patient_profile_id, type="lab_order.created",
                 actor_id=current.id, actor_label=current.email, lab_order_id=order.id)
    return _lab_payload(order)


@router.patch("/lab-orders/{order_id}")
def update_lab_order(
    order_id: int, body: dict, current: user, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    order = db.get(LabOrder, order_id)
    if order is None or order.is_deleted:
        raise AppError("NOT_FOUND", "lab order not found")
    for field in ("lab_name", "tests", "notes", "results_attachment_id"):
        if field in body:
            setattr(order, field, body[field])
    if "status" in body:
        order.status = body["status"]
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="lab_order.update", correlation_id=get_request_id(request),
        entity_type="lab_order", entity_id=str(order_id),
    ):
        db.commit()
    return _lab_payload(order)


@router.delete("/lab-orders/{order_id}")
def delete_lab_order(
    order_id: int, current: user, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    order = db.get(LabOrder, order_id)
    if order is None or order.is_deleted:
        raise AppError("NOT_FOUND", "lab order not found")
    order.is_deleted = True
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="lab_order.delete", correlation_id=get_request_id(request),
        entity_type="lab_order", entity_id=str(order_id),
    ):
        db.commit()
    return {"ok": True}
