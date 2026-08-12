"""Visit service (Plan/05 E1–E4, E7): create/open, versioned autosave,
completion (drives queue + appointment + billing hook), diagnoses,
prescriptions, follow-ups, and the non-null timeline projection."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError
from app.models.emr import (
    Attachment,
    Prescription,
    PrescriptionItem,
    Visit,
    VisitDiagnosis,
)
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.queueing import QueueEntry
from app.models.scheduling import Appointment

EDIT_WINDOW_HOURS = 24

TIMELINE_FIELDS = [
    "chief_complaint",
    "vitals",
    "clinical_exam",
    "findings",
    "labs",
    "imaging",
    "plan",
    "notes_next_visit",
]


def _now() -> datetime:
    return datetime.now(UTC)


def get_visit(db: Session, visit_id: int) -> Visit:
    visit = db.get(Visit, visit_id)
    if visit is None:
        raise AppError("NOT_FOUND", "visit not found")
    return visit


def create(
    db: Session,
    audit_db: Session,
    *,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
    queue_entry_id: int | None = None,
    patient_profile_id: int | None = None,
    visit_type_id: int | None = None,
) -> Visit:
    """Creates an open visit from a queue entry (idempotent re-enter) or adhoc."""
    doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == actor.id))
    if actor.role != "admin" and doctor is None:
        raise AppError("FORBIDDEN", "only doctors can create visits")

    if queue_entry_id is not None:
        existing = db.scalar(select(Visit).where(Visit.queue_entry_id == queue_entry_id))
        if existing is not None:
            return existing
        entry = db.get(QueueEntry, queue_entry_id)
        if entry is None:
            raise AppError("NOT_FOUND", "queue entry not found")
        if actor.role != "admin" and entry.doctor_id != doctor.id:
            raise AppError("FORBIDDEN", "not your queue entry")
        if entry.visit_type_id is None:
            raise AppError("CONFLICT", "queue entry has no visit type")
        visit = Visit(
            patient_profile_id=entry.patient_profile_id,
            doctor_id=entry.doctor_id,
            appointment_id=entry.appointment_id,
            queue_entry_id=entry.id,
            visit_type_id=entry.visit_type_id,
            started_at=_now(),
            status="open",
            last_saved_by=actor.id,
        )
    else:
        if patient_profile_id is None or visit_type_id is None:
            raise AppError(
                "VALIDATION", "patient_profile_id and visit_type_id required for adhoc visits"
            )
        if db.get(PatientProfile, patient_profile_id) is None:
            raise AppError("NOT_FOUND", "patient profile not found")
        visit = Visit(
            patient_profile_id=patient_profile_id,
            doctor_id=doctor.id if actor.role != "admin" else None,
            visit_type_id=visit_type_id,
            started_at=_now(),
            status="open",
            last_saved_by=actor.id,
        )
        if visit.doctor_id is None:
            raise AppError("VALIDATION", "admin cannot create adhoc visits without a doctor")

    db.add(visit)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="visit.create", correlation_id=correlation_id,
        entity_type="visit", entity_id=str(visit.id),
        after={"patient": visit.patient_profile_id, "status": "open"},
        ip=ip,
    ):
        db.commit()
    return visit


def _check_editable(db: Session, visit: Visit, actor: StaffUser) -> None:
    if visit.status == "completed":
        ended = visit.ended_at or visit.updated_at
        from app.core.timeutil import ensure_aware

        if ensure_aware(ended) < _now() - timedelta(hours=EDIT_WINDOW_HOURS):
            raise AppError("CONFLICT", "edit window expired; admin correction required")
        author = db.get(StaffUser, visit.last_saved_by) if visit.last_saved_by else None
        if actor.role != "admin" and (author is None or author.id != actor.id):
            raise AppError("FORBIDDEN", "only the author doctor can correct within the edit window")


def patch(
    db: Session,
    audit_db: Session,
    *,
    visit: Visit,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
    fields: dict,
    expected_version: int,
) -> Visit:
    _check_editable(db, visit, actor)
    doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == actor.id))
    if actor.role != "admin" and (doctor is None or doctor.id != visit.doctor_id):
        raise AppError("FORBIDDEN", "not your visit")
    if visit.record_version != expected_version:
        raise AppError("CONFLICT", "record changed; reload and review")

    if "visit_type_id" in fields or "custom_type_name" in fields:
        if visit.status != "open":
            raise AppError("CONFLICT", "visit type can only change while the visit is open")
        if fields.get("custom_type_name") and fields.get("visit_type_id") is None:
            raise AppError("VALIDATION", "a custom procedure name needs a procedure visit type")
        if fields.get("visit_type_id") is not None:
            from app.models.scheduling import VisitType

            visit_type = db.get(VisitType, fields["visit_type_id"])
            if visit_type is None or not visit_type.is_active:
                raise AppError("NOT_FOUND", "visit type not found")

    before = {"record_version": visit.record_version}
    for field, value in fields.items():
        setattr(visit, field, value)
    if "follow_up_weeks" in fields and fields["follow_up_weeks"] is not None:
        base = (visit.started_at or _now()).date()
        visit.follow_up_due = base + timedelta(weeks=fields["follow_up_weeks"])
    elif "follow_up_weeks" in fields and fields["follow_up_weeks"] is None:
        visit.follow_up_due = None
    visit.record_version += 1
    visit.last_saved_by = actor.id
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="visit.update", correlation_id=correlation_id,
        entity_type="visit", entity_id=str(visit.id),
        before=before, after={"record_version": visit.record_version},
        ip=ip,
    ):
        db.commit()
    return visit


def set_diagnoses(
    db: Session,
    audit_db: Session,
    *,
    visit: Visit,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
    items: list[dict],
    expected_version: int,
) -> list[VisitDiagnosis]:
    _check_editable(db, visit, actor)
    if visit.record_version != expected_version:
        raise AppError("CONFLICT", "record changed; reload and review")
    existing = db.scalars(
        select(VisitDiagnosis)
        .where(VisitDiagnosis.visit_id == visit.id)
        .order_by(VisitDiagnosis.order)
    ).all()
    for row in existing:
        db.delete(row)
    for idx, item in enumerate(items):
        db.add(
            VisitDiagnosis(
                visit_id=visit.id,
                kind=item["kind"],
                label=item["label"],
                icd10_code=item.get("icd10_code"),
                notes=item.get("notes"),
                order=idx,
            )
        )
    visit.record_version += 1
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="visit.diagnoses", correlation_id=correlation_id,
        entity_type="visit", entity_id=str(visit.id),
        after={"record_version": visit.record_version},
        ip=ip,
    ):
        db.commit()
    rows = db.scalars(
        select(VisitDiagnosis)
        .where(VisitDiagnosis.visit_id == visit.id)
        .order_by(VisitDiagnosis.order)
    ).all()
    return list(rows)


def complete(
    db: Session,
    audit_db: Session,
    *,
    visit: Visit,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Visit:
    if visit.status == "completed":
        raise AppError("CONFLICT", "visit already completed")
    doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == actor.id))
    if actor.role != "admin" and (doctor is None or doctor.id != visit.doctor_id):
        raise AppError("FORBIDDEN", "not your visit")

    before = {"status": visit.status}
    visit.status = "completed"
    visit.ended_at = _now()
    visit.record_version += 1

    entry = db.get(QueueEntry, visit.queue_entry_id) if visit.queue_entry_id else None
    if entry is not None and entry.status != "completed":
        entry.status = "completed"
        entry.ended_at = visit.ended_at
    appt = db.get(Appointment, visit.appointment_id) if visit.appointment_id else None
    if appt is not None and appt.status not in ("completed", "cancelled", "no_show"):
        appt.status = "completed"

    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="visit.complete", correlation_id=correlation_id,
        entity_type="visit", entity_id=str(visit.id),
        before=before, after={"status": "completed", "ended_at": visit.ended_at.isoformat()},
        ip=ip,
    ):
        db.commit()

    return visit


def reopen(
    db: Session,
    audit_db: Session,
    *,
    visit: Visit,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
) -> Visit:
    if visit.status != "completed":
        raise AppError("CONFLICT", "only completed visits can be reopened")
    if actor.role != "admin":
        ended = visit.ended_at or visit.updated_at
        from app.core.timeutil import ensure_aware

        if ensure_aware(ended) >= _now() - timedelta(hours=EDIT_WINDOW_HOURS):
            raise AppError("CONFLICT", "reopen is for corrections after the edit window")
        doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == actor.id))
        if doctor is None or doctor.id != visit.doctor_id:
            raise AppError("FORBIDDEN", "not your visit")
    visit.status = "open"
    visit.record_version += 1
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="visit.reopen", correlation_id=correlation_id,
        entity_type="visit", entity_id=str(visit.id),
        after={"status": "open"}, ip=ip,
    ):
        db.commit()
    return visit


def visit_type_display_name(db: Session, visit: Visit) -> str:
    """The invoice/cashier label: a custom procedure name wins over the type."""
    if visit.custom_type_name:
        return visit.custom_type_name
    from app.models.scheduling import VisitType

    visit_type = db.get(VisitType, visit.visit_type_id)
    return visit_type.name if visit_type else "Visit"


# ------------------------------------------------------------- prescriptions


def get_prescription(db: Session, visit_id: int) -> dict | None:
    rx = db.scalar(select(Prescription).where(Prescription.visit_id == visit_id))
    if rx is None:
        return None
    items = db.scalars(
        select(PrescriptionItem).where(PrescriptionItem.prescription_id == rx.id).order_by(
            PrescriptionItem.order
        )
    ).all()
    return {
        "id": rx.id,
        "notes": rx.notes,
        "items": [
            {
                "id": i.id,
                "medication_id": i.medication_id,
                "free_text": i.free_text,
                "dose": i.dose,
                "frequency": i.frequency,
                "duration": i.duration,
                "instructions": i.instructions,
                "quantity": i.quantity,
            }
            for i in items
        ],
    }


def put_prescription(
    db: Session,
    audit_db: Session,
    *,
    visit: Visit,
    actor: StaffUser,
    correlation_id: str,
    ip: str | None,
    notes: str | None,
    items: list[dict],
    expected_version: int,
) -> dict:
    _check_editable(db, visit, actor)
    if visit.record_version != expected_version:
        raise AppError("CONFLICT", "record changed; reload and review")
    rx = db.scalar(select(Prescription).where(Prescription.visit_id == visit.id))
    if rx is None:
        rx = Prescription(visit_id=visit.id, notes=notes, issued_by=actor.id)
        db.add(rx)
        db.flush()
    else:
        rx.notes = notes
    old_items = db.scalars(
        select(PrescriptionItem).where(PrescriptionItem.prescription_id == rx.id)
    ).all()
    for row in old_items:
        db.delete(row)
    for idx, item in enumerate(items):
        if item.get("medication_id") is None and not item.get("free_text"):
            raise AppError("VALIDATION", "each item needs a medication or free text")
        db.add(
            PrescriptionItem(
                prescription_id=rx.id,
                medication_id=item.get("medication_id"),
                free_text=item.get("free_text"),
                dose=item["dose"],
                frequency=item["frequency"],
                duration=item["duration"],
                instructions=item.get("instructions"),
                quantity=item.get("quantity"),
                order=idx,
            )
        )
    visit.record_version += 1
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=actor.id, actor_label=actor.email,
        action="visit.prescription", correlation_id=correlation_id,
        entity_type="visit", entity_id=str(visit.id),
        after={"record_version": visit.record_version},
        ip=ip,
    ):
        db.commit()
    return get_prescription(db, visit.id)


# --------------------------------------------------------------- timeline


def timeline(db: Session, profile_id: int, viewer: StaffUser) -> list[dict]:
    visits = db.scalars(
        select(Visit)
        .where(Visit.patient_profile_id == profile_id)
        .order_by(Visit.started_at.desc(), Visit.id.desc())
        .limit(50)
    ).all()
    return [_timeline_card(db, v, viewer) for v in visits]


def _timeline_card(db: Session, visit: Visit, viewer: StaffUser) -> dict:
    diagnoses = db.scalars(
        select(VisitDiagnosis)
        .where(VisitDiagnosis.visit_id == visit.id)
        .order_by(VisitDiagnosis.kind, VisitDiagnosis.order)
    ).all()
    doctor_name = None
    if visit.doctor_id:
        doctor = db.get(Doctor, visit.doctor_id)
        if doctor:
            user = db.get(StaffUser, doctor.staff_user_id)
            doctor_name = user.full_name if user else None
    card: dict = {
        "id": visit.id,
        "date": (visit.started_at or visit.created_at).date().isoformat(),
        "doctor_name": doctor_name,
        "visit_type_id": visit.visit_type_id,
        "status": visit.status,
        "has_rx": db.scalar(
            select(Prescription).where(Prescription.visit_id == visit.id)
        ) is not None,
        "attachments_count": len(
            db.scalars(
                select(Attachment.id).where(Attachment.visit_id == visit.id)
            ).all()
        ),
    }
    # non-null clinical fields only (E4) — the client renders these cards
    for field in TIMELINE_FIELDS:
        value = getattr(visit, field)
        if value is not None:
            card[field] = value
    finals = [d for d in diagnoses if d.kind == "final"]
    if finals:
        card["diagnoses"] = [d.label for d in finals]
    return card
