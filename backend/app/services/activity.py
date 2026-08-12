"""Activity stream service + hook helpers (Plan/14 C2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityEvent


def log_activity(
    db: Session,
    *,
    patient_profile_id: int,
    type: str,
    actor_type: str = "staff",
    actor_id: int | None = None,
    actor_label: str | None = None,
    **data,
) -> ActivityEvent:
    """Append an activity event for a patient's timeline."""
    event = ActivityEvent(
        patient_profile_id=patient_profile_id,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        type=type,
        data=data,
    )
    db.add(event)
    db.commit()
    return event


def list_activity(db: Session, profile_id: int, limit: int = 50) -> list[dict]:
    rows = db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.patient_profile_id == profile_id)
        .order_by(ActivityEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": e.id,
            "type": e.type,
            "actor_type": e.actor_type,
            "actor_label": e.actor_label,
            "data": e.data,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]
