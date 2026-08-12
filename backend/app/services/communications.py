"""Communication log service (Plan/14 C3)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.comms_log import CommunicationLogEntry


def log_communication(
    db: Session,
    *,
    patient_profile_id: int,
    channel: str,
    summary: str,
    staff_id: int | None = None,
) -> CommunicationLogEntry:
    entry = CommunicationLogEntry(
        patient_profile_id=patient_profile_id,
        channel=channel,
        summary=summary,
        staff_id=staff_id,
    )
    db.add(entry)
    db.commit()
    return entry


def list_communications(db: Session, profile_id: int, limit: int = 100) -> list[dict]:
    rows = db.scalars(
        select(CommunicationLogEntry)
        .where(CommunicationLogEntry.patient_profile_id == profile_id)
        .order_by(CommunicationLogEntry.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": e.id,
            "channel": e.channel,
            "summary": e.summary,
            "staff_id": e.staff_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]
