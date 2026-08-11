"""Medication DB routes (Plan/05 §3): search + doctor/admin management."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_role
from app.core.errors import AppError
from app.models.emr import Medication
from app.models.identity import StaffUser
from app.schemas.emr import MedicationCreate, MedicationUpdate

router = APIRouter(prefix="/api/medications", tags=["medications"])
staff = Annotated[StaffUser, Depends(require_role("admin", "doctor", "secretary"))]
clinical = Annotated[StaffUser, Depends(require_role("admin", "doctor"))]


@router.get("")
def search_medications(
    current: staff,
    db: DbDep,
    q: str = Query(default="", max_length=100),
):
    stmt = select(Medication).where(Medication.is_active.is_(True)).order_by(Medication.name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Medication.name.ilike(like),
                Medication.name_ar.ilike(like),
                Medication.form.ilike(like),
            )
        )
    rows = db.scalars(stmt.limit(20)).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "name_ar": m.name_ar,
            "form": m.form,
            "strength": m.strength,
            "default_dose": m.default_dose,
            "default_frequency": m.default_frequency,
            "default_duration": m.default_duration,
        }
        for m in rows
    ]


@router.post("")
def create_medication(
    body: MedicationCreate,
    current: clinical,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    med = Medication(**body.model_dump())
    db.add(med)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="medication.create", correlation_id=get_request_id(request),
        entity_type="medication", entity_id=str(med.id),
        after={"name": med.name, "form": med.form, "strength": med.strength},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": med.id, "name": med.name}


@router.patch("/{medication_id}")
def update_medication(
    medication_id: int,
    body: MedicationUpdate,
    current: clinical,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    med = db.get(Medication, medication_id)
    if med is None:
        raise AppError("NOT_FOUND", "medication not found")
    before = {"name": med.name, "is_active": med.is_active}
    for field in body.model_fields_set:
        setattr(med, field, getattr(body, field))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="medication.update", correlation_id=get_request_id(request),
        entity_type="medication", entity_id=str(medication_id),
        before=before, after={"name": med.name, "is_active": med.is_active},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {"id": med.id, "name": med.name}
