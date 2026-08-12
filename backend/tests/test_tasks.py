"""Internal tasks tests (Plan/14 C5)."""

import secrets
from datetime import date, timedelta

from tests.test_financial import admin_headers

TODAY = date.today()


def _make_task(client, admin, **kw):
    body = {"title": "Follow up", **kw}
    resp = client.post(
        "/api/tasks", json=body,
        headers={**admin, "Idempotency-Key": f"tk-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_task_crud_and_status_filter(client):
    admin = admin_headers(client)
    task = _make_task(client, admin, due_at=(TODAY + timedelta(days=1)).isoformat(),
                      priority="high")
    assert task["priority"] == "high"
    assert task["status"] == "open"

    # status filter
    rows = client.get("/api/tasks?status=open", headers=admin).json()["items"]
    assert any(t["id"] == task["id"] for t in rows)

    # update to done
    resp = client.patch(f"/api/tasks/{task['id']}", json={"status": "done"}, headers=admin)
    assert resp.status_code == 200, resp.text
    rows = client.get("/api/tasks?status=done", headers=admin).json()["items"]
    assert any(t["id"] == task["id"] for t in rows)

    # delete soft-removes
    client.delete(f"/api/tasks/{task['id']}", headers=admin)
    rows = client.get("/api/tasks", headers=admin).json()["items"]
    assert all(t["id"] != task["id"] for t in rows)


def test_task_bad_date_rejected(client):
    admin = admin_headers(client)
    resp = client.post("/api/tasks", json={"title": "x", "due_at": "not-a-date"}, headers=admin)
    assert resp.status_code == 422


def test_task_assignment_and_notification(client):
    admin = admin_headers(client)
    from app.db.session import SessionLocal
    from app.models.identity import StaffUser
    from app.services.roles import role_id as _rid

    db = SessionLocal()
    sec = StaffUser(
        email=f"tk-sec-{secrets.token_hex(4)}@example.com",
        password_hash="x", full_name="Task Sec",
        role_id=_rid(db, "secretary"), is_active=True,
    )
    db.add(sec)
    db.commit()
    sec_id = sec.id
    db.close()

    task = _make_task(client, admin, assigned_to=sec_id)
    assert task["assigned_to"] == sec_id

    db = SessionLocal()
    from sqlalchemy import select

    from app.models.comms import Notification

    rows = db.scalars(
        select(Notification).where(
            Notification.staff_user_id == sec_id, Notification.type == "task_new"
        )
    ).all()
    db.close()
    assert rows, "assignee was not notified of the new task"
