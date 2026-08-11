"""Queue service (Plan/04 Q1–Q9): same-day arrival queue per (doctor, date).

State machine: waiting -> called -> in_room -> completed | left.
Only a completed visit can complete its queue entry and appointment (Phase 05
owns that transition; the service function is defined here so Phase 05 can
call it).
"""

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError
from app.models.emr import Visit
from app.models.identity import PatientProfile
from app.models.queueing import QueueEntry
from app.models.scheduling import Appointment
from app.services.broadcast import queue_broadcaster
from app.services.sequences import next_booking_ref


def _now() -> datetime:
    return datetime.now(UTC)


def _entry_payload(entry: QueueEntry, db: Session) -> dict:
    profile = db.get(PatientProfile, entry.patient_profile_id)
    appt = db.get(Appointment, entry.appointment_id) if entry.appointment_id else None
    return {
        "id": entry.id,
        "seq": entry.seq,
        "doctor_id": entry.doctor_id,
        "date": entry.date.isoformat(),
        "appointment_id": entry.appointment_id,
        "patient_profile_id": entry.patient_profile_id,
        "patient_name": profile.full_name if profile else None,
        "visit_type_id": entry.visit_type_id,
        "status": entry.status,
        "checked_in_at": entry.checked_in_at.isoformat() if entry.checked_in_at else None,
        "called_at": entry.called_at.isoformat() if entry.called_at else None,
        "started_at": entry.started_at.isoformat() if entry.started_at else None,
        "ended_at": entry.ended_at.isoformat() if entry.ended_at else None,
        "booked_time": appt.start_time.strftime("%H:%M") if appt and appt.start_time else None,
        "late": (
            appt is not None
            and appt.start_time is not None
            and entry.checked_in_at is not None
            and entry.checked_in_at.strftime("%H:%M") > appt.start_time.strftime("%H:%M")
        ),
    }


def _next_seq(db: Session, doctor_id: int, target: date) -> int:
    current = db.scalar(
        select(func.max(QueueEntry.seq)).where(
            QueueEntry.doctor_id == doctor_id, QueueEntry.date == target
        )
    )
    return (current or 0) + 1


def _publish(entry: QueueEntry) -> None:
    queue_broadcaster.publish(
        queue_broadcaster.key(entry.doctor_id, entry.date),
        {"event": "entry_updated", "id": entry.id},
    )


def check_in(
    db: Session,
    audit_db: Session,
    *,
    appointment: Appointment,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> QueueEntry:
    if appointment.status != "booked":
        raise AppError(
            "CONFLICT", f"appointment is {appointment.status}, not bookable for check-in"
        )
    if db.scalar(
        select(QueueEntry).where(QueueEntry.appointment_id == appointment.id)
    ) is not None:
        raise AppError("CONFLICT", "already checked in")

    entry = QueueEntry(
        doctor_id=appointment.doctor_id,
        date=appointment.date,
        seq=_next_seq(db, appointment.doctor_id, appointment.date),
        appointment_id=appointment.id,
        patient_profile_id=appointment.patient_profile_id,
        visit_type_id=appointment.visit_type_id,
        status="waiting",
        checked_in_at=_now(),
    )
    before = {"status": appointment.status}
    appointment.status = "checked_in"
    db.add(entry)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.check_in", correlation_id=correlation_id,
        entity_type="queue_entry", entity_id=str(entry.id),
        before=before, after={"seq": entry.seq, "appointment": appointment.id},
        ip=ip,
    ):
        db.commit()
    _publish(entry)
    return entry


def walk_in(
    db: Session,
    audit_db: Session,
    *,
    doctor_id: int,
    visit_type_id: int,
    profile: PatientProfile,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
    target_date: date,
) -> QueueEntry:
    from app.models.identity import Doctor

    if db.get(Doctor, doctor_id) is None:
        raise AppError("NOT_FOUND", "doctor not found")

    appointment = Appointment(
        booking_ref=next_booking_ref(db),
        patient_profile_id=profile.id,
        doctor_id=doctor_id,
        visit_type_id=visit_type_id,
        date=target_date,
        start_time=None,  # walk-ins never occupy a slot
        status="booked",
        source="walk_in",
    )
    db.add(appointment)
    db.flush()
    appointment.status = "checked_in"

    entry = QueueEntry(
        doctor_id=doctor_id,
        date=target_date,
        seq=_next_seq(db, doctor_id, target_date),
        appointment_id=appointment.id,
        patient_profile_id=profile.id,
        visit_type_id=visit_type_id,
        status="waiting",
        checked_in_at=_now(),
    )
    db.add(entry)
    db.flush()
    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.walk_in", correlation_id=correlation_id,
        entity_type="queue_entry", entity_id=str(entry.id),
        after={"seq": entry.seq, "profile": profile.id, "appointment": appointment.id},
        ip=ip,
    ):
        db.commit()
    _publish(entry)
    return entry


def call_next(
    db: Session,
    audit_db: Session,
    *,
    doctor_id: int,
    target: date,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> QueueEntry | None:
    entry = db.scalar(
        select(QueueEntry)
        .where(
            QueueEntry.doctor_id == doctor_id,
            QueueEntry.date == target,
            QueueEntry.status == "waiting",
        )
        .order_by(QueueEntry.seq)
        .limit(1)
    )
    if entry is None:
        return None
    return call_entry(
        db, audit_db, entry=entry,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        correlation_id=correlation_id, ip=ip,
    )


def call_entry(
    db: Session,
    audit_db: Session,
    *,
    entry: QueueEntry,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> QueueEntry:
    if entry.status != "waiting":
        raise AppError("CONFLICT", f"entry is {entry.status}")
    entry.status = "called"
    entry.called_at = _now()
    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.call", correlation_id=correlation_id,
        entity_type="queue_entry", entity_id=str(entry.id),
        after={"status": "called"}, ip=ip,
    ):
        db.commit()
    _publish(entry)
    return entry


def start(
    db: Session,
    audit_db: Session,
    *,
    entry: QueueEntry,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> QueueEntry:
    if entry.status not in ("called", "waiting"):
        raise AppError("CONFLICT", f"entry is {entry.status}")
    active = db.scalar(
        select(func.count()).select_from(QueueEntry).where(
            QueueEntry.doctor_id == entry.doctor_id,
            QueueEntry.date == entry.date,
            QueueEntry.status == "in_room",
        )
    )
    if active:
        raise AppError("CONFLICT", "another patient is already in the room")
    entry.status = "in_room"
    entry.started_at = _now()
    if entry.visit_type_id is None:
        raise AppError("CONFLICT", "walk-in must declare a visit type")
    visit = Visit(
        patient_profile_id=entry.patient_profile_id,
        doctor_id=entry.doctor_id,
        appointment_id=entry.appointment_id,
        queue_entry_id=entry.id,
        visit_type_id=entry.visit_type_id,
        started_at=entry.started_at,
        status="open",
    )
    db.add(visit)
    db.flush()
    appt = db.get(Appointment, entry.appointment_id) if entry.appointment_id else None
    if appt is not None and appt.status in ("booked", "checked_in"):
        appt.status = "in_progress"
    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.start", correlation_id=correlation_id,
        entity_type="queue_entry", entity_id=str(entry.id),
        after={"status": "in_room", "visit": visit.id}, ip=ip,
    ):
        db.commit()
    _publish(entry)
    return entry


def complete(
    db: Session,
    audit_db: Session,
    *,
    entry: QueueEntry,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> QueueEntry:
    """Completes the queue entry and appointment — called after the linked
    visit is completed (Phase 05 owns the visit side)."""
    if entry.status != "in_room":
        raise AppError("CONFLICT", f"entry is {entry.status}")
    visit = db.scalar(
        select(Visit).where(Visit.queue_entry_id == entry.id)
    )
    if visit is None or visit.status != "completed":
        raise AppError("CONFLICT", "visit must be completed first")
    entry.status = "completed"
    entry.ended_at = _now()
    appt = db.get(Appointment, entry.appointment_id) if entry.appointment_id else None
    if appt is not None:
        appt.status = "completed"
    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.complete", correlation_id=correlation_id,
        entity_type="queue_entry", entity_id=str(entry.id),
        after={"status": "completed"}, ip=ip,
    ):
        db.commit()
    _publish(entry)
    return entry


def leave(
    db: Session,
    audit_db: Session,
    *,
    entry: QueueEntry,
    outcome: str,
    reason: str | None,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> QueueEntry:
    if entry.status in ("completed", "left"):
        raise AppError("CONFLICT", f"entry is {entry.status}")
    entry.status = "left"
    appt = db.get(Appointment, entry.appointment_id) if entry.appointment_id else None
    if appt is not None and appt.status not in ("completed", "cancelled", "no_show"):
        if outcome == "no_show":
            appt.status = "no_show"
            profile = db.get(PatientProfile, entry.patient_profile_id)
            if profile is not None:
                profile.no_show_count += 1
        else:
            appt.status = "cancelled"
            appt.cancel_reason = reason or "left_after_check_in"
            appt.cancelled_by = f"{actor_type}:{actor_id}"
    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.leave", correlation_id=correlation_id,
        entity_type="queue_entry", entity_id=str(entry.id),
        after={"status": "left", "outcome": outcome}, ip=ip,
    ):
        db.commit()
    _publish(entry)
    return entry


def reorder(
    db: Session,
    audit_db: Session,
    *,
    entry: QueueEntry,
    direction: str,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> QueueEntry:
    if entry.status != "waiting":
        raise AppError("CONFLICT", "only waiting entries can be reordered")
    neighbors = db.scalars(
        select(QueueEntry).where(
            QueueEntry.doctor_id == entry.doctor_id,
            QueueEntry.date == entry.date,
            QueueEntry.status == "waiting",
            QueueEntry.id != entry.id,
        ).order_by(QueueEntry.seq)
    ).all()
    if direction == "up":
        target = max((n for n in neighbors if n.seq < entry.seq), key=lambda n: n.seq, default=None)
    elif direction == "down":
        target = min((n for n in neighbors if n.seq > entry.seq), key=lambda n: n.seq, default=None)
    else:
        raise AppError("VALIDATION", "direction must be up or down")
    if target is None:
        return entry
    before = {"seq": entry.seq}
    entry.seq, target.seq = target.seq, entry.seq
    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.reorder", correlation_id=correlation_id,
        entity_type="queue_entry", entity_id=str(entry.id),
        before=before, after={"seq": entry.seq}, ip=ip,
    ):
        db.commit()
    _publish(entry)
    _publish(target)
    return entry


def close_day(
    db: Session,
    audit_db: Session,
    *,
    doctor_id: int,
    target: date,
    actor_type: str,
    actor_id: int | None,
    actor_label: str,
    correlation_id: str,
    ip: str | None,
) -> dict:
    """Q8: waiting -> left (appointments cancelled left_after_check_in);
    untouched booked -> no_show (counter once); in-room = exceptions."""
    waiting = db.scalars(
        select(QueueEntry).where(
            QueueEntry.doctor_id == doctor_id,
            QueueEntry.date == target,
            QueueEntry.status == "waiting",
        )
    ).all()
    left_count = 0
    for entry in waiting:
        entry.status = "left"
        appt = db.get(Appointment, entry.appointment_id) if entry.appointment_id else None
        if appt is not None and appt.status in ("booked", "checked_in"):
            appt.status = "cancelled"
            appt.cancel_reason = "left_after_check_in"
            appt.cancelled_by = f"{actor_type}:{actor_id}"
        left_count += 1

    booked = db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.date == target,
            Appointment.status == "booked",
        )
    ).all()
    no_show_count = 0
    for appt in booked:
        appt.status = "no_show"
        profile = db.get(PatientProfile, appt.patient_profile_id)
        if profile is not None:
            profile.no_show_count += 1
        no_show_count += 1

    in_room = db.scalar(
        select(func.count()).select_from(QueueEntry).where(
            QueueEntry.doctor_id == doctor_id,
            QueueEntry.date == target,
            QueueEntry.status == "in_room",
        )
    )

    with audit.audited_action(
        audit_db,
        actor_type=actor_type, actor_id=actor_id, actor_label=actor_label,
        action="queue.close_day", correlation_id=correlation_id,
        entity_type="queue", entity_id=f"{doctor_id}:{target.isoformat()}",
        after={"left": left_count, "no_show": no_show_count, "in_room_exceptions": in_room or 0},
        ip=ip,
    ):
        db.commit()
    for entry in waiting:
        _publish(entry)
    return {"left": left_count, "no_show": no_show_count, "in_room_exceptions": in_room or 0}
