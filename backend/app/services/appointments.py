"""Appointment lifecycle service (Plan/03 R7–R12): book / move / cancel /
no-show, with capacity validation and audit. Idempotency keys are claimed by
routes and completed here after commit."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError
from app.models.identity import Doctor, PatientProfile
from app.models.scheduling import Appointment, VisitType
from app.services.availability import validate_booking
from app.services.idempotency import complete
from app.services.sequences import next_booking_ref


def acquire_day_lock(db: Session, doctor_id: int, target: date) -> None:
    """Serializes capacity decisions for one (doctor, day).

    Postgres: row lock via FOR UPDATE on the sequence row.
    SQLite: a write statement takes the database write lock, so a concurrent
    transaction's validation cannot observe stale counts (Plan/03 §4).
    """
    scope = f"booking_lock:{doctor_id}:{target.isoformat()}"
    from app.models.identity import NumberSequence

    row = db.scalar(
        select(NumberSequence)
        .where(NumberSequence.scope == scope, NumberSequence.year.is_(None))
        .with_for_update()
    )
    if row is None:
        db.add(NumberSequence(scope=scope, year=None, value=0))
        db.flush()
    else:
        row.value += 1  # write to hold the lock
        db.flush()


def _now() -> datetime:
    return datetime.now(UTC)


def _end_time(start: time, visit_type: VisitType, doctor: Doctor) -> time:
    minutes = visit_type.duration_minutes or doctor.default_slot_minutes
    base = datetime.combine(date.today(), start) + timedelta(minutes=minutes)
    return base.time()


def _appointment_payload(appt: Appointment) -> dict:
    return {
        "id": appt.id,
        "booking_ref": appt.booking_ref,
        "patient_profile_id": appt.patient_profile_id,
        "doctor_id": appt.doctor_id,
        "visit_type_id": appt.visit_type_id,
        "date": appt.date.isoformat(),
        "start_time": appt.start_time.strftime("%H:%M") if appt.start_time else None,
        "status": appt.status,
        "source": appt.source,
        "follow_up_of_id": appt.follow_up_of_id,
    }


def get_doctor(db: Session, doctor_id: int) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise AppError("NOT_FOUND", "doctor not found")
    return doctor


def get_visit_type(db: Session, visit_type_id: int) -> VisitType:
    vt = db.get(VisitType, visit_type_id)
    if vt is None or not vt.is_active:
        raise AppError("NOT_FOUND", "visit type not found")
    return vt


def book(
    db: Session,
    audit_db: Session,
    *,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
    patient_profile_id: int,
    doctor_id: int,
    visit_type_id: int,
    target_date: date,
    start_time: time | None,
    source: str,
    force: bool = False,
    follow_up_of_id: int | None = None,
    idempotency_key: str | None = None,
) -> Appointment:
    profile = db.get(PatientProfile, patient_profile_id)
    if profile is None or profile.is_archived:
        raise AppError("NOT_FOUND", "patient profile not found")
    doctor = get_doctor(db, doctor_id)
    visit_type = get_visit_type(db, visit_type_id)

    if source == "public" and follow_up_of_id is not None:
        raise AppError("FORBIDDEN", "public bookings cannot link follow-ups")
    acquire_day_lock(db, doctor.id, target_date)
    ok, reason = validate_booking(
        db, doctor, visit_type, target_date, start_time, public=(source == "public"), force=force
    )
    if not ok:
        raise AppError("CONFLICT", f"not available: {reason}")

    appt = Appointment(
        booking_ref=next_booking_ref(db),
        patient_profile_id=profile.id,
        doctor_id=doctor.id,
        visit_type_id=visit_type.id,
        date=target_date,
        start_time=start_time,
        end_time=_end_time(start_time, visit_type, doctor) if start_time else None,
        status="booked",
        source=source,
        follow_up_of_id=follow_up_of_id,
        booked_by_staff_id=actor_id if actor_type == "staff" else None,
    )
    db.add(appt)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action="appointment.create",
        correlation_id=correlation_id,
        entity_type="appointment",
        entity_id=str(appt.id),
        after=_appointment_payload(appt),
        ip=ip,
    ):
        db.commit()

    if idempotency_key:
        complete(
            db,
            owner_type=actor_type,
            owner_id=actor_id,
            key=idempotency_key,
            status=200,
            body=_appointment_payload(appt),
        )
    return appt


def move(
    db: Session,
    audit_db: Session,
    *,
    appt: Appointment,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
    new_date: date,
    new_start: time | None,
    idempotency_key: str | None = None,
) -> Appointment:
    if appt.status not in ("booked", "checked_in"):
        raise AppError("CONFLICT", f"cannot move appointment in status {appt.status}")
    doctor = get_doctor(db, appt.doctor_id)
    visit_type = get_visit_type(db, appt.visit_type_id)
    acquire_day_lock(db, doctor.id, new_date)
    ok, reason = validate_booking(db, doctor, visit_type, new_date, new_start, public=False)
    if not ok:
        raise AppError("CONFLICT", f"not available: {reason}")

    before = _appointment_payload(appt)
    appt.date = new_date
    appt.start_time = new_start
    appt.end_time = _end_time(new_start, visit_type, doctor) if new_start else None
    with audit.audited_action(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action="appointment.move",
        correlation_id=correlation_id,
        entity_type="appointment",
        entity_id=str(appt.id),
        before=before,
        after=_appointment_payload(appt),
        ip=ip,
    ):
        db.commit()
    return appt


def cancel(
    db: Session,
    audit_db: Session,
    *,
    appt: Appointment,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
    reason: str | None = None,
) -> Appointment:
    if appt.status == "no_show":
        raise AppError("CONFLICT", "cannot cancel a no-show; create a new appointment instead")
    if appt.status in ("completed", "cancelled"):
        raise AppError("CONFLICT", f"appointment already {appt.status}")
    if actor_type == "patient" and appt.status != "booked":
        raise AppError("FORBIDDEN", "patients may only cancel before check-in")

    before = _appointment_payload(appt)
    appt.status = "cancelled"
    appt.cancel_reason = reason
    appt.cancelled_by = f"{actor_type}:{actor_id}"
    with audit.audited_action(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action="appointment.cancel",
        correlation_id=correlation_id,
        entity_type="appointment",
        entity_id=str(appt.id),
        before=before,
        after=_appointment_payload(appt),
        ip=ip,
    ):
        db.commit()
    return appt


def mark_no_show(
    db: Session,
    audit_db: Session,
    *,
    appt: Appointment,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> Appointment:
    if appt.status != "booked":
        raise AppError(
            "CONFLICT", f"only booked appointments can be marked no-show (status: {appt.status})"
        )
    before = _appointment_payload(appt)
    appt.status = "no_show"
    profile = db.get(PatientProfile, appt.patient_profile_id)
    assert profile is not None
    profile.no_show_count += 1
    with audit.audited_action(
        audit_db,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action="appointment.no_show",
        correlation_id=correlation_id,
        entity_type="appointment",
        entity_id=str(appt.id),
        before=before,
        after=_appointment_payload(appt),
        ip=ip,
    ):
        db.commit()
    return appt
