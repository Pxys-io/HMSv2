"""Internal task endpoints (Plan/14 C5)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.audit import service as audit
from app.core.deps import AuditDbDep, DbDep, get_request_id, require_perm
from app.core.errors import AppError
from app.models.identity import StaffUser
from app.models.tasks import Task
from app.services.notify import fan_out

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
user = Annotated[StaffUser, Depends(require_perm("ops.task"))]


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AppError("VALIDATION", "due_at must be YYYY-MM-DD") from exc


def _payload(t: Task, current: StaffUser) -> dict:
    return {
        "id": t.id, "title": t.title, "notes": t.notes,
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "assigned_to": t.assigned_to, "priority": t.priority, "status": t.status,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "is_mine": t.assigned_to == current.id or t.assigned_to is None,
    }


@router.get("")
def list_tasks(
    current: user, db: DbDep,
    status: str | None = Query(default=None),
    assignee: int | None = Query(default=None),
    mine: bool = Query(default=False),
):
    stmt = select(Task).where(Task.is_deleted.is_(False))
    if status:
        stmt = stmt.where(Task.status == status)
    if mine:
        stmt = stmt.where(
            (Task.assigned_to == current.id) | (Task.assigned_to.is_(None))
        )
    elif assignee is not None:
        stmt = stmt.where(Task.assigned_to == assignee)
    rows = db.scalars(
        stmt.order_by(Task.due_at.is_(None), Task.due_at, Task.id.desc())
    ).all()
    return {"items": [_payload(t, current) for t in rows]}


@router.post("")
def create_task(
    body: dict, current: user, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    title = str(body.get("title", "")).strip()
    if not title:
        raise AppError("VALIDATION", "title is required")
    task = Task(
        title=title,
        notes=body.get("notes"),
        due_at=_parse_date(body.get("due_at")),
        assigned_to=body.get("assigned_to"),
        priority=body.get("priority", "medium"),
        status="open",
        created_by=current.id,
    )
    db.add(task)
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="task.create", correlation_id=get_request_id(request),
        entity_type="task", entity_id="0", after={"title": title},
    ):
        db.commit()
    if task.assigned_to:
        from app.api.routes.notifications import broadcast_notification

        for notification in fan_out(
            db, type="task_new", title="New task assigned to you", body=title,
            link="/tasks", staff_id=task.assigned_to,
        ):
            broadcast_notification(notification.staff_user_id, {
                "type": "task_new", "title": notification.title, "body": title,
                "notification_id": notification.id,
            })
        db.commit()
    return _payload(task, current)


@router.patch("/{task_id}")
def update_task(
    task_id: int, body: dict, current: user, request: Request,
    db: DbDep, audit_db: AuditDbDep,
):
    task = db.get(Task, task_id)
    if task is None or task.is_deleted:
        raise AppError("NOT_FOUND", "task not found")
    for field in ("title", "notes", "assigned_to", "priority", "status"):
        if field in body:
            setattr(task, field, body[field])
    if "due_at" in body:
        task.due_at = _parse_date(body["due_at"])
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="task.update", correlation_id=get_request_id(request),
        entity_type="task", entity_id=str(task_id),
    ):
        db.commit()
    return _payload(task, current)


@router.delete("/{task_id}")
def delete_task(
    task_id: int, current: user, request: Request, db: DbDep, audit_db: AuditDbDep,
):
    task = db.get(Task, task_id)
    if task is None or task.is_deleted:
        raise AppError("NOT_FOUND", "task not found")
    task.is_deleted = True
    with audit.audited_action(
        audit_db,
        actor_type="staff", actor_id=current.id, actor_label=current.email,
        action="task.delete", correlation_id=get_request_id(request),
        entity_type="task", entity_id=str(task_id),
    ):
        db.commit()
    return {"ok": True}
