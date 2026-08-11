"""Audit viewer endpoints (Plan/02 §4.5–4.6): browse, verify, reconcile,
export. Admin only."""

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select

from app.audit import service as audit
from app.audit.models import AuditEvent
from app.core.deps import AuditDbDep, require_role
from app.core.errors import AppError
from app.core.pagination import paginate
from app.models.identity import StaffUser

router = APIRouter(prefix="/api/audit", tags=["audit"])
admin = Annotated[StaffUser, Depends(require_role("admin"))]


def _payload(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "actor_label": event.actor_label,
        "action": event.action,
        "outcome": event.outcome,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "correlation_id": event.correlation_id,
        "before_json": event.before_json,
        "after_json": event.after_json,
        "context_json": event.context_json,
        "ip": event.ip,
    }


@router.get("/events")
def list_events(
    current: admin,
    audit_db: AuditDbDep,
    from_date: Annotated[datetime | None, Query(alias="from")] = None,
    to_date: Annotated[datetime | None, Query(alias="to")] = None,
    actor: str | None = Query(default=None, max_length=200),
    action_prefix: str | None = Query(default=None, max_length=60),
    entity_type: str | None = Query(default=None, max_length=60),
    outcome: str | None = Query(default=None, pattern="^(intent|committed|aborted|access)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc())
    if from_date is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= from_date)
    if to_date is not None:
        stmt = stmt.where(AuditEvent.occurred_at <= to_date)
    if actor is not None:
        stmt = stmt.where(AuditEvent.actor_label.ilike(f"%{actor}%"))
    if action_prefix is not None:
        stmt = stmt.where(AuditEvent.action.startswith(action_prefix))
    if entity_type is not None:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if outcome is not None:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    result = paginate(audit_db, stmt, page, page_size)
    result["items"] = [_payload(e) for e in result["items"]]
    return result


@router.get("/events/{event_id}")
def get_event(event_id: int, current: admin, audit_db: AuditDbDep):
    event = audit_db.get(AuditEvent, event_id)
    if event is None:
        raise AppError("NOT_FOUND", "event not found")
    return _payload(event)


@router.post("/verify")
def verify_chain(current: admin, audit_db: AuditDbDep):
    return audit.verify(audit_db)


@router.post("/reconcile")
def reconcile_chain(current: admin, audit_db: AuditDbDep):
    count = audit.reconcile(audit_db)
    return {"reconciled": count}


@router.get("/export")
def export_events(
    current: admin,
    audit_db: AuditDbDep,
    from_date: Annotated[datetime, Query(alias="from")],
    to_date: Annotated[datetime, Query(alias="to")],
):
    rows = audit_db.scalars(
        select(AuditEvent)
        .where(AuditEvent.occurred_at >= from_date, AuditEvent.occurred_at <= to_date)
        .order_by(AuditEvent.id)
    ).all()
    lines = [json.dumps(_payload(e), ensure_ascii=False) for e in rows]
    return Response(
        content="\n".join(lines),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=audit.ndjson"},
    )
