"""Staff patient-profile routes: create, view, per-patient appointments
(Plan/03 §3.1, Plan/05 demographics)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.core.pagination import paginate
from app.models.identity import PatientProfile, StaffUser
from app.models.scheduling import Appointment
from app.schemas.scheduling import PatientProfileCreate, PatientProfileUpdate
from app.services.activity import list_activity, log_activity
from app.services.communications import list_communications, log_communication
from app.services.sequences import next_patient_code


class CommunicationCreate(BaseModel):
    channel: Literal["call", "email", "whatsapp", "sms", "in_person"] = "call"
    summary: str = Field(min_length=1, max_length=2000)


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
        "tags": [{"id": t.id, "name": t.name} for t in profile.tags],
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
    if custom_data is not None:
        payload["custom_data"] = custom_data
    from app.services.patient_form import validate_payload

    validated = validate_payload(db, payload)
    profile = PatientProfile(
        code=next_patient_code(db),
        **validated["fixed"],
        custom_data=validated["custom_data"],
    )
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
    log_activity(db, patient_profile_id=profile.id, type="patient.created",
                 actor_id=current.id, actor_label=current.email)
    return _payload(profile)


@router.get("/{profile_id}")
def get_patient(profile_id: int, current: staff, db: DbDep):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    return _payload(profile)


@router.get("/{profile_id}/communications")
def get_communications(
    profile_id: int,
    current: staff,
    db: DbDep,
    limit: int = Query(default=100, ge=1, le=500),
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    return {"items": list_communications(db, profile_id, limit)}


@router.post("/{profile_id}/communications")
def create_communication(
    profile_id: int,
    body: CommunicationCreate,
    current: staff,
    db: DbDep,
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    entry = log_communication(
        db,
        patient_profile_id=profile_id,
        channel=body.channel,
        summary=body.summary,
        staff_id=current.id,
    )
    return {
        "id": entry.id, "channel": entry.channel, "summary": entry.summary,
        "staff_id": entry.staff_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get("/{profile_id}/activity")
def get_activity(
    profile_id: int,
    current: staff,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None:
        raise AppError("NOT_FOUND", "patient profile not found")
    return {"items": list_activity(db, profile_id, limit)}


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
    patch_payload = body.model_dump(exclude_unset=True)
    from app.services.patient_form import validate_payload

    validated = validate_payload(db, patch_payload, partial=True)
    for field, value in validated["fixed"].items():
        setattr(profile, field, value)
    if validated["custom_data"] is not None:
        profile.custom_data = {
            **(profile.custom_data or {}),
            **validated["custom_data"],
        }
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="patient_profile.demographics", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile_id),
        before=before, after=_payload(profile),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    changed = [f for f in body.model_fields_set if f != "custom_data"]
    log_activity(db, patient_profile_id=profile.id, type="patient.updated",
                 actor_id=current.id, actor_label=current.email, fields=changed)
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
