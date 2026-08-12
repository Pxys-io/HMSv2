"""In-app notifications (Plan/08 N1–N2): fan-out rows + SSE bell."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.comms import Notification
from app.models.identity import StaffUser


def _now() -> datetime:
    return datetime.now(UTC)


def fan_out(
    db: Session,
    *,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    roles: tuple[str, ...] = ("admin", "secretary"),
    staff_id: int | None = None,
) -> list[Notification]:
    """Creates notification rows for matching staff (all admins/secretaries
    by default; a specific user when staff_id is given)."""
    stmt = select(StaffUser).where(StaffUser.is_active.is_(True))
    if staff_id is not None:
        stmt = stmt.where(StaffUser.id == staff_id)
    elif roles:
        from app.models.identity import Role

        role_ids = db.scalars(
            select(Role.id).where(Role.name.in_(roles))
        ).all()
        stmt = stmt.where(StaffUser.role_id.in_(role_ids))
    users = db.scalars(stmt).all()
    notifications = [
        Notification(staff_user_id=u.id, type=type, title=title, body=body, link=link)
        for u in users
    ]
    for notification in notifications:
        db.add(notification)
    db.flush()
    return notifications
