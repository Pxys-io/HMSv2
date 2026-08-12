"""Notifications + WhatsApp reminder routes (Plan/08 §5)."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_current_staff, get_request_id
from app.core.errors import AppError
from app.models.comms import Notification
from app.models.identity import StaffUser
from app.models.scheduling import Appointment
from app.services import reminders as reminders_service
from app.services.broadcast import Broadcaster

router = APIRouter(prefix="/api", tags=["notifications-reminders"])
Staff = Annotated[StaffUser, Depends(get_current_staff)]

notify_broadcaster = Broadcaster()


def _user_key(staff_id: int) -> tuple[str, int]:
    return ("user", staff_id)


def broadcast_notification(staff_id: int, notification: dict) -> None:
    notify_broadcaster.publish(_user_key(staff_id), {"event": "notification", **notification})


# -------------------------------------------------------------- notifications


@router.get("/notifications")
def list_notifications(current: Staff, db: DbDep, unread_only: bool = Query(default=False)):
    stmt = (
        select(Notification)
        .where(Notification.staff_user_id == current.id)
        .order_by(Notification.id.desc())
        .limit(50)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt).all()
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "read": n.read_at is not None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, current: Staff, db: DbDep):
    notification = db.get(Notification, notification_id)
    if notification is None or notification.staff_user_id != current.id:
        raise AppError("NOT_FOUND", "notification not found")
    notification.read_at = datetime.now(UTC)
    db.commit()
    return {"id": notification_id, "read": True}


@router.post("/notifications/read-all")
def mark_all_read(current: Staff, db: DbDep):
    rows = db.scalars(
        select(Notification).where(
            Notification.staff_user_id == current.id, Notification.read_at.is_(None)
        )
    ).all()
    for row in rows:
        row.read_at = datetime.now(UTC)
    db.commit()
    return {"marked": len(rows)}


@router.get("/notifications/stream")
async def notification_stream(current: Staff):
    key = _user_key(current.id)
    subscription = notify_broadcaster.subscribe(key)

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
            notify_broadcaster.unsubscribe(key, subscription)

    return EventSourceResponse(gen())


# --------------------------------------------------------------- reminders


@router.get("/appointments/{appointment_id}/reminder-link")
def appointment_reminder_link(
    appointment_id: int,
    current: Staff,
    request: Request,
    db: DbDep,
    audit_db: AuditDbDep,
    locale: str = Query(default="ar", pattern="^(ar|en)$"),
):
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise AppError("NOT_FOUND", "appointment not found")
    result = reminders_service.reminder_link(db, appointment, locale)
    if result["url"] is not None:
        from app.services.communications import log_communication

        appointment.reminder_link_generated_at = datetime.now(UTC)
        log_communication(
            db,
            patient_profile_id=appointment.patient_profile_id,
            channel="whatsapp",
            summary=f"Reminder link generated for {appointment.date.isoformat()}",
            staff_id=current.id,
        )
        db.commit()
    audit.access(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="reminder.link_generated", entity_type="appointment",
        entity_id=str(appointment_id),
        correlation_id=get_request_id(request),
        ip=request.client.host if request.client else None,
    )
    return result


@router.get("/appointments/reminders/today")
def upcoming_reminders(
    current: Staff,
    db: DbDep,
    doctor_id: int | None = Query(default=None),
    locale: str = Query(default="ar", pattern="^(ar|en)$"),
):
    return reminders_service.upcoming_reminders(db, doctor_id, locale)
