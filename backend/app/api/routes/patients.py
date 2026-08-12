"""Staff patient-profile routes: create, view, per-patient appointments
(Plan/03 §3.1, Plan/05 demographics)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.core.pagination import paginate
from app.models.identity import PatientProfile, StaffUser
from app.models.scheduling import Appointment
from app.schemas.scheduling import PatientProfileCreate, PatientProfileUpdate
from app.services.custom_fields import validate_and_coerce as _validate_custom
from app.services.sequences import next_patient_code

router = APIRouter(prefix="/api/patients", tags=["patients"])
staff = Annotated[StaffUser, Depends(require_perm("patient.view"))]


def _payload(profile: PatientProfile) -> dict:
    age = None
    if profile.birth_date:
        from datetime import date

        age = (date.today() - profile.birth_date).days // 365
    return {
        "id": profile.id,
        "code": profile.code,
        "full_name": profile.full_name,
        "full_name_ar": profile.full_name_ar,
        "gender": profile.gender,
        "birth_date": profile.birth_date.isoformat() if profile.birth_date else None,
        "age": age,
        "phone": profile.phone,
        "phone_alt": profile.phone_alt,
        "address": profile.address,
        "has_allergies": bool(profile.allergies),
        "has_chronic_conditions": bool(profile.chronic_conditions),
        "no_show_count": profile.no_show_count,
        "is_archived": profile.is_archived,
        "record_version": profile.record_version,
        "custom_data": profile.custom_data,
    }


@router.post("")
def create_patient(
    body: PatientProfileCreate,
    current: staff,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    payload = body.model_dump()
    custom_data = payload.pop("custom_data", None)
    profile = PatientProfile(code=next_patient_code(db), **payload)
    if custom_data is not None:
        profile.custom_data = _validate_custom(db, "patient", custom_data)
    db.add(profile)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="patient_profile.create", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile.id),
        after={"code": profile.code, "name": profile.full_name},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(profile)


@router.get("/{profile_id}")
def get_patient(profile_id: int, current: staff, db: DbDep):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    return _payload(profile)


@router.get("/{profile_id}/appointments")
def patient_appointments(
    profile_id: int,
    current: staff,
    db: DbDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if db.get(PatientProfile, profile_id) is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    stmt = (
        select(Appointment)
        .where(Appointment.patient_profile_id == profile_id)
        .order_by(Appointment.date.desc(), Appointment.start_time.desc())
    )
    result = paginate(db, stmt, page, page_size)
    result["items"] = [
        {
            "id": a.id,
            "booking_ref": a.booking_ref,
            "doctor_id": a.doctor_id,
            "visit_type_id": a.visit_type_id,
            "date": a.date.isoformat(),
            "start_time": a.start_time.strftime("%H:%M") if a.start_time else None,
            "status": a.status,
            "source": a.source,
        }
        for a in result["items"]
    ]
    return result


@router.patch("/{profile_id}/demographics")
def patch_demographics(
    profile_id: int,
    body: PatientProfileUpdate,
    current: staff,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    before = _payload(profile)
    for field in body.model_fields_set:
        if field == "custom_data":
            profile.custom_data = _validate_custom(db, "patient", getattr(body, field))
            continue
        setattr(profile, field, getattr(body, field))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="patient_profile.demographics", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile_id),
        before=before, after=_payload(profile),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(profile)


class _ClinicalAlerts(BaseModel):
    allergies: str | None = None
    chronic_conditions: str | None = None


@router.patch("/{profile_id}/clinical-alerts")
def patch_clinical_alerts(
    profile_id: int,
    body: _ClinicalAlerts,
    current: Annotated[StaffUser, Depends(require_perm("patient.edit", "emr.write"))],
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    before = {"allergies": profile.allergies, "chronic_conditions": profile.chronic_conditions}
    for field in body.model_fields_set:
        setattr(profile, field, getattr(body, field))
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="patient_profile.clinical_alerts", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile_id),
        before=before,
        after={"allergies": profile.allergies, "chronic_conditions": profile.chronic_conditions},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return {
        "allergies": profile.allergies,
        "chronic_conditions": profile.chronic_conditions,
    }
