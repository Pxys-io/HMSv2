"""Automated reminder tests (Plan/14 C11)."""

import secrets
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.db.session import SessionLocal
from tests.test_financial import admin_headers

TOMORROW = date.today() + timedelta(days=1)


@pytest.fixture(autouse=True)
def _clean_reminder_settings(client):
    from tests.test_financial import admin_headers

    admin = admin_headers(client)
    client.put("/api/settings", json={
        "reminder.sms_gateway_url": "",
        "reminder.sms_token": "",
        "reminder.sms_sender": "",
    }, headers=admin)


def _book_for_tomorrow(client, admin, clinic, phone, email=None):
    pid = clinic["profile_id"]
    client.patch(f"/api/patients/{pid}/demographics", json={"phone": phone}, headers=admin)
    if email:
        from app.db.session import SessionLocal as DB
        from app.models.identity import PatientAccount, PatientProfile

        db = DB()
        account = PatientAccount(full_name="R", email=email, password_hash="x",
                                 locale="ar", is_active=True)
        db.add(account)
        db.flush()
        profile = db.get(PatientProfile, pid)
        profile.account_id = account.id
        db.commit()
        db.close()
    resp = client.post(
        "/api/appointments",
        json={"patient_profile_id": pid, "doctor_id": clinic["doctor_id"],
              "visit_type_id": clinic["visit_type_id"], "date": TOMORROW.isoformat(),
              "start_time": "18:00"},
        headers={**admin, "Idempotency-Key": f"rm-{secrets.token_hex(4)}"},
    )
    assert resp.status_code == 200, resp.text
    return pid


def test_sms_reminder_via_gateway(client, clinic):
    admin = admin_headers(client)
    client.put("/api/settings", json={
        "reminder.sms_gateway_url": "http://localhost:9999/send",
        "reminder.sms_token": "t0k3n",
        "reminder.sms_sender": "Clinic",
    }, headers=admin)
    pid = _book_for_tomorrow(client, admin, clinic, "01012345678")

    from app.services import reminder_jobs

    with patch.object(reminder_jobs, "_send_sms") as send:
        result = reminder_jobs.run_once()
        assert result["sms"] == 1
        send.assert_called_once()
        args = send.call_args[0]
        assert args[3] == "201012345678"  # normalized with country code 20
    # idempotent: second sweep sends nothing
    with patch.object(reminder_jobs, "_send_sms") as send:
        result = reminder_jobs.run_once()
        assert result["sms"] == 0
        send.assert_not_called()
    # C3 hook: communication log has the SMS entry
    rows = client.get(f"/api/patients/{pid}/communications", headers=admin).json()["items"]
    assert any(r["channel"] == "sms" for r in rows)


def test_no_gateway_skips_sms(client, clinic):
    admin = admin_headers(client)
    _book_for_tomorrow(client, admin, clinic, "01012345678")
    from app.services import reminder_jobs

    with patch.object(reminder_jobs, "_send_sms") as send:
        result = reminder_jobs.run_once()
    assert result["sms"] == 0
    send.assert_not_called()


def test_email_reminder_queued(client, clinic):
    admin = admin_headers(client)
    email = f"rm-{secrets.token_hex(4)}@example.com"
    _book_for_tomorrow(client, admin, clinic, "01012345678", email=email)
    from app.services import reminder_jobs

    result = reminder_jobs.run_once()
    assert result["email"] == 1
    db = SessionLocal()
    from sqlalchemy import select

    from app.models.comms import OutboxEvent

    events = db.scalars(select(OutboxEvent).where(OutboxEvent.kind == "email_reminder")).all()
    db.close()
    assert events and events[0].payload["to"] == email
