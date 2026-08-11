"""Availability engine (Plan/03 §4) — the single source of truth for both
preview and commit. Both booking modes, capacity-aware, block-aware."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.identity import Doctor
from app.models.scheduling import Appointment, DoctorSchedule, ScheduleBlock, VisitType
from app.services.settings import booking_horizon_days, clinic_now

ACTIVE_STATUSES = ("booked", "checked_in", "in_progress")

GRACE_MINUTES = 10


def _merge_intervals(intervals: list[tuple[time, time]]) -> list[tuple[time, time]]:
    """Merge overlapping/adjacent shift intervals for one weekday."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda i: (i[0], i[1]))
    merged: list[tuple[time, time]] = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def active_shifts(db: Session, doctor_id: int, target: date) -> list[tuple[time, time]]:
    rows = db.scalars(
        select(DoctorSchedule).where(
            DoctorSchedule.doctor_id == doctor_id,
            DoctorSchedule.is_active.is_(True),
            (DoctorSchedule.effective_from.is_(None)) | (DoctorSchedule.effective_from <= target),
            (DoctorSchedule.effective_to.is_(None)) | (DoctorSchedule.effective_to >= target),
        )
    ).all()
    intervals = [(r.start_time, r.end_time) for r in rows if r.weekday == target.weekday()]
    return _merge_intervals(intervals)


def is_blocked(db: Session, doctor_id: int, target: date) -> bool:
    return (
        db.scalar(
            select(func.count()).select_from(ScheduleBlock).where(
                ScheduleBlock.doctor_id == doctor_id,
                ScheduleBlock.date_from <= target,
                ScheduleBlock.date_to >= target,
            )
        )
        > 0
    )


def active_day_count(db: Session, doctor_id: int, target: date) -> int:
    return db.scalar(
        select(func.count()).select_from(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.date == target,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
    ) or 0


def active_slot_count(db: Session, doctor_id: int, target: date, start: time) -> int:
    return db.scalar(
        select(func.count()).select_from(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.date == target,
            Appointment.start_time == start,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
    ) or 0


def _in_past(target: date, start: time) -> bool:
    now = clinic_now()
    if target < now.date():
        return True
    if target > now.date():
        return False
    return datetime.combine(target, start, tzinfo=now.tzinfo) <= now + timedelta(
        minutes=GRACE_MINUTES
    )


def day_availability(
    db: Session,
    doctor: Doctor,
    target: date,
    visit_type: VisitType,
    *,
    public: bool = False,
) -> dict:
    """Returns the availability payload for one doctor-day."""
    if is_blocked(db, doctor.id, target):
        return {"mode": doctor.booking_mode, "date": target.isoformat(), "slots": None,
            "remaining": 0,
                "reason": "block"}
    shifts = active_shifts(db, doctor.id, target)
    if not shifts:
        return {"mode": doctor.booking_mode, "date": target.isoformat(), "slots": None,
            "remaining": 0,
                "reason": "no_shift"}

    day_count = active_day_count(db, doctor.id, target)
    if doctor.day_capacity is not None and day_count >= doctor.day_capacity:
        return {"mode": doctor.booking_mode, "date": target.isoformat(), "slots": None,
            "remaining": 0,
                "reason": "capacity"}

    if public:
        horizon = booking_horizon_days(db)
        if target > (clinic_now().date() + timedelta(days=horizon)):
            return {"mode": doctor.booking_mode, "date": target.isoformat(), "slots": None,
                "remaining": 0,
                    "reason": "horizon"}

    if doctor.booking_mode == "day_queue":
        remaining = None
        if doctor.day_capacity is not None:
            remaining = doctor.day_capacity - day_count
        return {"mode": "day_queue", "date": target.isoformat(), "slots": None,
            "remaining": remaining,
                "reason": None}

    length = visit_type.duration_minutes or doctor.default_slot_minutes
    step = timedelta(minutes=length + doctor.buffer_minutes)
    slot_len = timedelta(minutes=length)

    slots: list[dict] = []
    for shift_start, shift_end in shifts:
        cursor = datetime.combine(target, shift_start)
        end_boundary = datetime.combine(target, shift_end)
        while cursor + slot_len <= end_boundary:
            start_time = cursor.time()
            if not _in_past(target, start_time):
                taken = active_slot_count(db, doctor.id, target, start_time)
                remaining = doctor.slot_capacity - taken
                if remaining > 0:
                    slots.append(
                        {
                            "start": start_time.strftime("%H:%M"),
                            "end": (cursor + slot_len).time().strftime("%H:%M"),
                            "remaining": remaining,
                        }
                    )
            cursor += step
    return {"mode": "slots", "date": target.isoformat(), "slots": slots, "remaining": None,
        "reason": None}


def validate_booking(
    db: Session,
    doctor: Doctor,
    visit_type: VisitType,
    target: date,
    start_time: time | None,
    *,
    public: bool = False,
    force: bool = False,
) -> tuple[bool, str]:
    """Commit-time validation — rechecks everything against current data.

    Returns (ok, reason). Staff `force=True` bypasses capacity only; blocks,
    shift rules, and past-time rules still apply.
    """
    if is_blocked(db, doctor.id, target):
        return False, "block"
    shifts = active_shifts(db, doctor.id, target)
    if not shifts:
        return False, "no_shift"
    if public:
        if target > (clinic_now().date() + timedelta(days=booking_horizon_days(db))):
            return False, "horizon"
        if target < clinic_now().date():
            return False, "past"
    if (
        not force
        and doctor.day_capacity is not None
        and active_day_count(db, doctor.id, target) >= doctor.day_capacity
    ):
        return False, "capacity"

    if doctor.booking_mode == "slots":
        if start_time is None:
            return False, "slots_required"
        inside_shift = any(s <= start_time <= e for s, e in shifts)
        if not inside_shift:
            return False, "no_shift"
        if _in_past(target, start_time):
            return False, "past"
        if (
            not force
            and active_slot_count(db, doctor.id, target, start_time) >= doctor.slot_capacity
        ):
            return False, "capacity"
    else:
        if start_time is not None:
            return False, "day_queue_only"
    return True, "ok"
