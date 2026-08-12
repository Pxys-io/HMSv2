"""HR tests (Plan/14 F): attendance, leaves (F2 terminal states), leave
balances (F5), payroll math (F3), absent notification (F4)."""

import secrets
from datetime import date

from tests.test_financial import admin_headers

TODAY = date.today()


def _make_staff(db, **kw):
    from app.core.security import hash_password
    from app.models.identity import StaffUser
    from app.services.roles import role_id as _rid

    user = StaffUser(
        email=f"hr-{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("passw0rd"), full_name="HR Staff",
        role_id=_rid(db, "secretary"), is_active=True, **kw,
    )
    db.add(user)
    db.commit()
    return user


def test_attendance_clock_in_out(client):
    admin = admin_headers(client)
    resp = client.post("/api/hr/attendance/clock-in", headers=admin)
    assert resp.status_code == 200, resp.text
    # duplicate clock-in rejected
    resp = client.post("/api/hr/attendance/clock-in", headers=admin)
    assert resp.status_code == 422
    resp = client.post("/api/hr/attendance/clock-out", headers=admin)
    assert resp.status_code == 200, resp.text
    # clock-out again rejected
    resp = client.post("/api/hr/attendance/clock-out", headers=admin)
    assert resp.status_code == 422
    month = TODAY.strftime("%Y-%m")
    rows = client.get(f"/api/hr/attendance?month={month}", headers=admin).json()["items"]
    assert any(r["date"] == TODAY.isoformat() for r in rows)


def test_leave_flow_and_f2_terminal_state(client):
    admin = admin_headers(client)
    db = __import__("app.db.session", fromlist=["SessionLocal"]).SessionLocal()
    _make_staff(db, base_salary=10000)
    db.close()

    # secretary applies for leave (as the staff member themselves)
    resp = client.post(
        "/api/hr/leaves",
        json={"leave_type": "annual", "from_date": TODAY.isoformat(),
              "to_date": (TODAY).isoformat(), "reason": "vacation"},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    leave = resp.json()
    assert leave["days"] == 1
    assert leave["status"] == "pending"

    # admin approves
    resp = client.patch(f"/api/hr/leaves/{leave['id']}", json={"status": "approved"},
                        headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"

    # F2: approved -> rejected is forbidden
    resp = client.patch(f"/api/hr/leaves/{leave['id']}", json={"status": "rejected"},
                        headers=admin)
    assert resp.status_code == 422

    # F5: leave balances reflect the approved day
    balances = client.get("/api/hr/leave-balances", headers=admin).json()
    assert balances["year"] == TODAY.year
    assert balances["balances"].get("annual", 0) >= 1.0


def test_payroll_math_f3(client):
    admin = admin_headers(client)
    db = __import__("app.db.session", fromlist=["SessionLocal"]).SessionLocal()
    from app.models.identity import StaffUser

    user = db.get(StaffUser, 1)
    user.base_salary = 10000
    user.allowances = 1000
    user.deductions = 500
    user.tax_pct = 10
    user.social_insurance = 300
    db.commit()
    db.close()

    month = "2026-08"
    resp = client.post("/api/hr/payroll/run", json={"month": month}, headers=admin)
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["month"] == month
    assert run["status"] == "draft"
    item = next(i for i in run["items"] if i["staff_user_id"] == 1)
    # F3: gross = 10000 + 1000 - 500 = 10500; tax = 10% = 1050; net = 10500-1050-300
    assert item["gross"] == 10500.0
    assert item["tax"] == 1050.0
    assert item["social_insurance"] == 300.0
    assert item["net"] == 9150.0

    # duplicate run rejected
    resp = client.post("/api/hr/payroll/run", json={"month": month}, headers=admin)
    assert resp.status_code == 409
    # GET returns the same run
    got = client.get(f"/api/hr/payroll?month={month}", headers=admin).json()
    assert got["items"][0]["net"] == 9150.0


def test_absent_notification_f4(client):
    from unittest.mock import patch

    from app.services import hr as hr_service

    with patch.object(hr_service, "clinic_now") as now:
        from datetime import datetime

        now.return_value = datetime(2026, 8, 12, 11, 30)
        hr_service.notify_absent_staff(
            __import__("app.db.session", fromlist=["SessionLocal"]).SessionLocal()
        )
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.comms import Notification

    db = SessionLocal()
    rows = db.scalars(
        select(Notification).where(Notification.type == "hr_absent")
    ).all()
    db.close()
    assert rows, "absence notification was not created"
