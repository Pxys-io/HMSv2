"""Public patient-profile endpoints (own family members only; Plan/11 §3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_current_patient, get_request_id, verify_csrf
from app.core.errors import AppError
from app.models.identity import PatientAccount, PatientProfile
from app.schemas.scheduling import PatientProfileCreate, PatientProfileUpdate
from app.services.sequences import next_patient_code

_csrf = Depends(verify_csrf)
router = APIRouter(prefix="/api/public/profiles", tags=["public-profiles"], dependencies=[_csrf])
Patient = Annotated[PatientAccount, Depends(get_current_patient)]


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
        "is_archived": profile.is_archived,
    }


@router.get("")
def list_profiles(current: Patient, db: DbDep):
    rows = db.scalars(
        select(PatientProfile).where(
            PatientProfile.account_id == current.id, PatientProfile.is_archived.is_(False)
        )
    ).all()
    return [_payload(p) for p in rows]


@router.post("")
def create_profile(
    body: PatientProfileCreate,
    current: Patient,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    profile = PatientProfile(
        code=next_patient_code(db), account_id=current.id, **body.model_dump()
    )
    db.add(profile)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="patient", actor_id=current.id, actor_label=current.full_name,
        action="patient_profile.create", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile.id),
        after={"code": profile.code, "name": profile.full_name},
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(profile)


@router.patch("/{profile_id}")
def update_profile(
    profile_id: int,
    body: PatientProfileUpdate,
    current: Patient,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
):
    profile = db.get(PatientProfile, profile_id)
    if profile is None or profile.account_id != current.id:
        raise AppError("FORBIDDEN", "not your profile")
    before = _payload(profile)
    for field in body.model_fields_set:
        setattr(profile, field, getattr(body, field))
    with audit.audited_action(
        audit_db,
        actor_type="patient", actor_id=current.id, actor_label=current.full_name,
        action="patient_profile.update", correlation_id=get_request_id(request),
        entity_type="patient_profile", entity_id=str(profile_id),
        before=before, after=_payload(profile),
        ip=request.client.host if request.client else None,
    ):
        db.commit()
    return _payload(profile)
