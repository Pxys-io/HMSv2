"""Queue routes (Plan/04 §3): board snapshot, mutations, SSE stream, TV display."""

import asyncio
import json
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.core.security import sha256_hex
from app.models.config import Setting
from app.models.identity import PatientProfile, StaffUser
from app.models.queueing import QueueEntry
from app.models.scheduling import Appointment
from app.schemas.scheduling import PatientProfileCreate
from app.services import queue as queue_service
from app.services.activity import log_activity
from app.services.broadcast import queue_broadcaster
from app.services.idempotency import claim, complete, get_key_from_request
from app.services.sequences import next_patient_code
from app.services.settings import clinic_today

router = APIRouter(prefix="/api/queue", tags=["queue"])
staff = Annotated[StaffUser, Depends(require_perm("queue.view"))]
secretary = Annotated[
    StaffUser, Depends(require_perm("queue.checkin", "queue.move", "queue.close_day"))
]
doctor_only = Annotated[StaffUser, Depends(require_perm("queue.start", "queue.complete"))]


class CheckInRequest(BaseModel):
    appointment_id: int


class WalkInRequest(BaseModel):
    doctor_id: int
    visit_type_id: int
    profile_id: int | None = None
    new_profile: PatientProfileCreate | None = None
    day: date | None = None  # defaults to clinic today


class LeaveRequest(BaseModel):
    outcome: str = Field(pattern="^(cancelled|no_show)$")
    reason: str | None = Field(default=None, max_length=300)


class MoveRequest(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


class CloseDayRequest(BaseModel):
    doctor_id: int
    day: date


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


def _booked_not_arrived(db: Session, doctor_id: int, target: date) -> list[dict]:
    rows = db.scalars(
        select(Appointment)
        .where(
            Appointment.doctor_id == doctor_id,
            Appointment.date == target,
            Appointment.status == "booked",
        )
        .order_by(Appointment.start_time)
    ).all()
    out = []
    for a in rows:
        profile = db.get(PatientProfile, a.patient_profile_id)
        out.append(
            {
                "id": a.id,
                "booking_ref": a.booking_ref,
                "patient_profile_id": a.patient_profile_id,
                "patient_name": profile.full_name if profile else None,
                "visit_type_id": a.visit_type_id,
                "start_time": a.start_time.strftime("%H:%M") if a.start_time else None,
            }
        )
    return out


def _snapshot(db: Session, doctor_id: int, target: date) -> dict:
    entries = db.scalars(
        select(QueueEntry)
        .where(QueueEntry.doctor_id == doctor_id, QueueEntry.date == target)
        .order_by(QueueEntry.seq)
    ).all()
    return {
        "doctor_id": doctor_id,
        "date": target.isoformat(),
        "entries": [_entry_payload(e, db) for e in entries],
        "booked_not_arrived": _booked_not_arrived(db, doctor_id, target),
    }


@router.get("")
def board_snapshot(
    current: staff,
    db: DbDep,
    doctor_id: Annotated[int, Query()],
    date: Annotated[date, Query()],
):
    return _snapshot(db, doctor_id, date)


# ------------------------------------------------------------ mutation helpers


def _claim_replay(
    request: Request, response: Response, db: Session, current: StaffUser, payload: dict
) -> bool:
    key = get_key_from_request(request)
    if not key:
        return False
    replay = claim(db, owner_type="staff", owner_id=current.id, key=key, payload=payload)
    if replay:
        response.status_code = replay["status"]
        response.body = json.dumps(replay["body"], ensure_ascii=False).encode()
        response.headers["Content-Type"] = "application/json"
        return True
    return False


def _finish_idem(request: Request, db: Session, current: StaffUser, body: dict) -> None:
    key = get_key_from_request(request)
    if key:
        complete(db, owner_type="staff", owner_id=current.id, key=key, status=200, body=body)


def _base_kwargs(request: Request, current: StaffUser) -> dict:
    return {
        "actor_type": "staff",
        "actor_id": current.id,
        "actor_label": current.email,
        "correlation_id": get_request_id(request),
        "ip": request.client.host if request.client else None,
    }


@router.post("/check-in")
def check_in(
    body: CheckInRequest,
    request: Request,
    response: Response,
    current: secretary,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _claim_replay(request, response, db, current, body.model_dump()):
        return response
    appt = db.get(Appointment, body.appointment_id)
    if appt is None:
        raise AppError("NOT_FOUND", "appointment not found")
    entry = queue_service.check_in(db, audit_db, appointment=appt, **_base_kwargs(request, current))
    log_activity(db, patient_profile_id=appt.patient_profile_id, type="appointment.checked_in",
                 actor_id=current.id, actor_label=current.email, entry_id=entry.id)
    payload = _entry_payload(entry, db)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/walk-in")
def walk_in(
    body: WalkInRequest,
    request: Request,
    response: Response,
    current: secretary,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _claim_replay(request, response, db, current, body.model_dump(mode="json")):
        return response
    if (body.profile_id is None) == (body.new_profile is None):
        raise AppError("VALIDATION", "provide exactly one of profile_id or new_profile")
    if body.profile_id is not None:
        profile = db.get(PatientProfile, body.profile_id)
        if profile is None:
            raise AppError("NOT_FOUND", "patient profile not found")
    else:
        profile = PatientProfile(code=next_patient_code(db), **body.new_profile.model_dump())
        db.add(profile)
        db.flush()
    target = body.day or clinic_today()
    entry = queue_service.walk_in(
        db, audit_db,
        doctor_id=body.doctor_id, visit_type_id=body.visit_type_id, profile=profile,
        target_date=target, **_base_kwargs(request, current),
    )
    log_activity(db, patient_profile_id=profile.id, type="walk_in.created",
                 actor_id=current.id, actor_label=current.email, entry_id=entry.id)
    payload = _entry_payload(entry, db)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/call-next")
def call_next(
    request: Request,
    response: Response,
    current: staff,
    db: DbDep,
    audit_db: AuditDbDep,
    doctor_id: Annotated[int, Query()],
    date: Annotated[date, Query()],
):
    if _claim_replay(
        request, response, db, current, {"doctor_id": doctor_id, "date": date.isoformat()}
    ):
        return response
    entry = queue_service.call_next(
        db, audit_db, doctor_id=doctor_id, target=date, **_base_kwargs(request, current)
    )
    payload = _entry_payload(entry, db) if entry else None
    _finish_idem(request, db, current, payload or {"no_entry": True})
    return payload


@router.post("/{entry_id}/call")
def call_entry(
    entry_id: int,
    request: Request,
    response: Response,
    current: staff,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _claim_replay(request, response, db, current, {"entry_id": entry_id}):
        return response
    entry = db.get(QueueEntry, entry_id)
    if entry is None:
        raise AppError("NOT_FOUND", "queue entry not found")
    updated = queue_service.call_entry(db, audit_db, entry=entry, **_base_kwargs(request, current))
    payload = _entry_payload(updated, db)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/{entry_id}/start")
def start_entry(
    entry_id: int,
    request: Request,
    response: Response,
    current: doctor_only,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _claim_replay(request, response, db, current, {"entry_id": entry_id}):
        return response
    entry = db.get(QueueEntry, entry_id)
    if entry is None:
        raise AppError("NOT_FOUND", "queue entry not found")
    updated = queue_service.start(db, audit_db, entry=entry, **_base_kwargs(request, current))
    log_activity(db, patient_profile_id=entry.patient_profile_id, type="visit.created",
                 actor_id=current.id, actor_label=current.email, entry_id=entry.id)
    payload = _entry_payload(updated, db)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/{entry_id}/complete")
def complete_entry(
    entry_id: int,
    request: Request,
    response: Response,
    current: doctor_only,
    db: DbDep,
    audit_db: AuditDbDep,
):
    """Compatibility action — normally the visit-completion flow (Phase 05)
    drives this transition."""
    if _claim_replay(request, response, db, current, {"entry_id": entry_id}):
        return response
    entry = db.get(QueueEntry, entry_id)
    if entry is None:
        raise AppError("NOT_FOUND", "queue entry not found")
    updated = queue_service.complete(db, audit_db, entry=entry, **_base_kwargs(request, current))
    payload = _entry_payload(updated, db)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/{entry_id}/leave")
def leave_entry(
    entry_id: int,
    body: LeaveRequest,
    request: Request,
    response: Response,
    current: secretary,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _claim_replay(request, response, db, current, {"entry_id": entry_id, **body.model_dump()}):
        return response
    entry = db.get(QueueEntry, entry_id)
    if entry is None:
        raise AppError("NOT_FOUND", "queue entry not found")
    updated = queue_service.leave(
        db, audit_db, entry=entry, outcome=body.outcome, reason=body.reason,
        **_base_kwargs(request, current),
    )
    payload = _entry_payload(updated, db)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/{entry_id}/move")
def move_entry(
    entry_id: int,
    body: MoveRequest,
    request: Request,
    response: Response,
    current: secretary,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _claim_replay(request, response, db, current, {"entry_id": entry_id, **body.model_dump()}):
        return response
    entry = db.get(QueueEntry, entry_id)
    if entry is None:
        raise AppError("NOT_FOUND", "queue entry not found")
    updated = queue_service.reorder(
        db, audit_db, entry=entry, direction=body.direction, **_base_kwargs(request, current)
    )
    payload = _entry_payload(updated, db)
    _finish_idem(request, db, current, payload)
    return payload


@router.post("/close-day")
def close_day(
    body: CloseDayRequest,
    request: Request,
    response: Response,
    current: secretary,
    db: DbDep,
    audit_db: AuditDbDep,
):
    if _claim_replay(request, response, db, current, body.model_dump(mode="json")):
        return response
    result = queue_service.close_day(
        db, audit_db, doctor_id=body.doctor_id, target=body.day, **_base_kwargs(request, current)
    )
    _finish_idem(request, db, current, result)
    return result


# ----------------------------------------------------------------------- SSE


async def _sse_generator(
    db: Session, doctor_id: int, target: date, current: StaffUser
):
    key = queue_broadcaster.key(doctor_id, target)
    subscription = queue_broadcaster.subscribe(key)
    try:
        snapshot = json.dumps(_snapshot(db, doctor_id, target), ensure_ascii=False)
        yield {"event": "snapshot", "data": snapshot}
        while True:
            try:
                message = await asyncio.wait_for(subscription.get(), timeout=15)
            except TimeoutError:
                yield ": ping"
                continue
            yield message
    finally:
        queue_broadcaster.unsubscribe(key, subscription)


@router.get("/stream")
async def queue_stream(
    current: staff,
    db: DbDep,
    doctor_id: Annotated[int, Query()],
    date: Annotated[date, Query()],
):
    return EventSourceResponse(_sse_generator(db, doctor_id, date, current))


# ----------------------------------------------------------- TV display (public)


def _display_token(doctor_id: int) -> str | None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        row = db.scalar(select(Setting).where(Setting.key == f"display_token_{doctor_id}"))
        return row.value if row is not None else None


def _check_display_token(doctor_id: int, token: str) -> None:
    stored = _display_token(doctor_id)
    if stored is None or stored != sha256_hex(token):
        raise AppError("FORBIDDEN", "invalid display token")


display_router = APIRouter(prefix="/api/queue/display", tags=["queue-display"])


@display_router.get("/{doctor_id}")
def display_snapshot(doctor_id: int, token: Annotated[str, Query()]):
    from app.db.session import SessionLocal as _SL

    _check_display_token(doctor_id, token)
    with _SL() as db:
        now_calling = db.scalar(
            select(QueueEntry).where(
                QueueEntry.doctor_id == doctor_id,
                QueueEntry.date == clinic_today(),
                QueueEntry.status == "in_room",
            )
        )
        waiting_count = len(
            db.scalars(
                select(QueueEntry).where(
                    QueueEntry.doctor_id == doctor_id,
                    QueueEntry.date == clinic_today(),
                    QueueEntry.status.in_(("waiting", "called")),
                )
            ).all()
        )
        calling = None
        if now_calling is not None:
            profile = db.get(PatientProfile, now_calling.patient_profile_id)
            calling = {
                "seq": now_calling.seq,
                "first_name": profile.full_name.split()[0] if profile else None,
            }
        return {"now_calling": calling, "waiting_count": waiting_count}


@display_router.get("/{doctor_id}/stream")
async def display_stream(doctor_id: int, token: str = Query(...)):
    _check_display_token(doctor_id, token)
    key = queue_broadcaster.key(doctor_id, clinic_today())
    subscription = queue_broadcaster.subscribe(key)

    async def gen():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(subscription.get(), timeout=15)
                except TimeoutError:
                    yield ": ping"
                    continue
                yield message
        finally:
            queue_broadcaster.unsubscribe(key, subscription)

    return EventSourceResponse(gen())
