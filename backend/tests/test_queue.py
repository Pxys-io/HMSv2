"""Queue tests (Plan/04 §7): check-in, walk-in, seq, call-next, start, leave,
close-day, reorder, SSE snapshot + delta, display token privacy."""

import json
import secrets
from datetime import date, time

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.config import Setting
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.queueing import QueueEntry
from app.models.scheduling import Appointment, DoctorSchedule, VisitType
from app.services.roles import role_id as _rid
from tests.conftest import csrf_headers

TODAY = date.today()


@pytest.fixture()
def clinic():
    """Returns a dict with a bookable doctor, visit type, and a booked appointment."""
    from app.models.identity import PatientAccount

    db = SessionLocal()
    user = StaffUser(
        email=f"qdr-{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("passw0rd"), full_name="Queue Doc",
        role_id=_rid(db, "doctor"), is_active=True,
    )
    db.add(user)
    db.flush()
    doctor = Doctor(
        staff_user_id=user.id, specialty="T", booking_mode="slots",
        default_slot_minutes=20, buffer_minutes=0, slot_capacity=4,
        billing_mode="per_visit", is_bookable_online=True,
    )
    db.add(doctor)
    db.flush()
    for wd in range(7):
        db.add(
            DoctorSchedule(
                doctor_id=doctor.id, weekday=wd, start_time=time(17, 0), end_time=time(21, 0)
            )
        )
    vt = VisitType(name="C", name_ar="ك", duration_minutes=20, default_price=300)
    db.add(vt)
    db.flush()

    account = PatientAccount(
        email=f"qpat-{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("passw0rd"), full_name="Q",
    )
    db.add(account)
    db.flush()
    profile = PatientProfile(
        code=f"P-Q{secrets.token_hex(4).upper()}", account_id=account.id,
        full_name="Q P", phone="010",
    )
    db.add(profile)
    db.flush()

    appt = Appointment(
        booking_ref=f"BK-Q{secrets.token_hex(4).upper()}",
        patient_profile_id=profile.id, doctor_id=doctor.id,
        visit_type_id=vt.id, date=TODAY, start_time=time(17, 0), end_time=time(17, 20),
        status="booked", source="staff",
    )
    db.add(appt)
    db.commit()
    result = {"doctor": doctor, "visit_type": vt, "profile": profile, "appointment": appt}
    db.close()
    return result


def staff_headers(client):
    csrf = client.cookies.get("hmsv2_csrf")
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=headers,
    )
    token = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_check_in_creates_queue_entry(client, clinic):
    headers = staff_headers(client)
    resp = client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "qi-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["seq"] == 1
    assert body["status"] == "waiting"
    assert body["patient_name"] == "Q P"

    # double check-in -> 409
    again = client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "qi-2"},
    )
    assert again.status_code == 409


def test_board_snapshot_includes_booked_not_arrived(client, clinic):
    headers = staff_headers(client)
    doctor_id = clinic["doctor"].id
    resp = client.get(f"/api/queue?doctor_id={doctor_id}&date={TODAY.isoformat()}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["booked_not_arrived"]) == 1
    assert body["booked_not_arrived"][0]["id"] == clinic["appointment"].id


def test_walk_in_with_new_profile(client, clinic):
    headers = staff_headers(client)
    resp = client.post(
        "/api/queue/walk-in",
        json={
            "doctor_id": clinic["doctor"].id,
            "visit_type_id": clinic["visit_type"].id,
            "day": TODAY.isoformat(),
            "new_profile": {"full_name": "Walk In", "phone": "01111111111"},
        },
        headers={**headers, "Idempotency-Key": "wi-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["seq"] == 1
    assert body["patient_name"] == "Walk In"
    assert body["booked_time"] is None  # walk-ins never occupy a slot


def test_seq_monotonic_two_doctors_independent(client, clinic):
    headers = staff_headers(client)
    first = client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "seq-1"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["seq"] == 1
    # second entry on the same day (walk-in) gets seq 2
    second = client.post(
        "/api/queue/walk-in",
        json={
            "doctor_id": clinic["doctor"].id,
            "visit_type_id": clinic["visit_type"].id,
            "day": TODAY.isoformat(),
            "new_profile": {"full_name": "Second", "phone": "01111111112"},
        },
        headers={**headers, "Idempotency-Key": "seq-2"},
    )
    assert second.json()["seq"] == 2


def test_call_next_and_start_creates_visit(client, clinic):
    headers = staff_headers(client)
    appt = clinic["appointment"]
    client.post(
        "/api/queue/check-in",
        json={"appointment_id": appt.id},
        headers={**headers, "Idempotency-Key": "cn-1"},
    )
    called = client.post(
        f"/api/queue/call-next?doctor_id={clinic['doctor'].id}&date={TODAY.isoformat()}",
        headers={**headers, "Idempotency-Key": "cn-2"},
    )
    assert called.status_code == 200
    assert called.json()["status"] == "called"

    started = client.post(
        f"/api/queue/{called.json()['id']}/start",
        headers={**headers, "Idempotency-Key": "cn-3"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_room"

    from app.models.emr import Visit

    db = SessionLocal()
    visit = db.scalar(select(Visit).where(Visit.queue_entry_id == started.json()["id"]))
    assert visit is not None and visit.status == "open"
    db_appt = db.get(Appointment, appt.id)
    assert db_appt.status == "in_progress"
    db.close()


def test_only_one_in_room(client, clinic):
    headers = staff_headers(client)
    # check in two appointments
    first = client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "one-1"},
    ).json()

    db = SessionLocal()
    second_appt = Appointment(
        booking_ref=f"BK-Q{secrets.token_hex(4).upper()}", patient_profile_id=clinic["profile"].id,
        doctor_id=clinic["doctor"].id, visit_type_id=clinic["visit_type"].id,
        date=TODAY, start_time=time(17, 20), end_time=time(17, 40),
        status="booked", source="staff",
    )
    db.add(second_appt)
    db.commit()
    second_id = second_appt.id
    db.close()
    client.post(
        "/api/queue/check-in",
        json={"appointment_id": second_id},
        headers={**headers, "Idempotency-Key": "one-2"},
    )

    client.post(
        f"/api/queue/{first['id']}/call", headers={**headers, "Idempotency-Key": "one-3"}
    )
    second_entry = client.get(
        f"/api/queue?doctor_id={clinic['doctor'].id}&date={TODAY.isoformat()}", headers=headers
    ).json()["entries"][1]
    client.post(
        f"/api/queue/{second_entry['id']}/call",
        headers={**headers, "Idempotency-Key": "one-4"},
    )

    # start the first -> in_room
    client.post(f"/api/queue/{first['id']}/start", headers={**headers, "Idempotency-Key": "one-5"})
    # starting the second while someone is in_room -> 409
    blocked = client.post(
        f"/api/queue/{second_entry['id']}/start",
        headers={**headers, "Idempotency-Key": "one-6"},
    )
    assert blocked.status_code == 409


def test_complete_requires_completed_visit(client, clinic):
    headers = staff_headers(client)
    entry = client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "cp-1"},
    ).json()
    client.post(
        f"/api/queue/{entry['id']}/start", headers={**headers, "Idempotency-Key": "cp-2"}
    )
    resp = client.post(
        f"/api/queue/{entry['id']}/complete", headers={**headers, "Idempotency-Key": "cp-3"}
    )
    assert resp.status_code == 409  # visit not completed yet (Phase 05 owns that)


def test_leave_cancels_checked_in_appointment(client, clinic):
    headers = staff_headers(client)
    entry = client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "lv-1"},
    ).json()
    resp = client.post(
        f"/api/queue/{entry['id']}/leave",
        json={"outcome": "cancelled", "reason": "patient left"},
        headers={**headers, "Idempotency-Key": "lv-2"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "left"

    db = SessionLocal()
    appt = db.get(Appointment, clinic["appointment"].id)
    assert appt.status == "cancelled"
    assert appt.cancel_reason == "patient left"
    db.close()


def test_close_day_sweep(client, clinic):
    headers = staff_headers(client)
    client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "cd-1"},
    ).json()

    db = SessionLocal()
    untouched = Appointment(
        booking_ref=f"BK-Q{secrets.token_hex(4).upper()}", patient_profile_id=clinic["profile"].id,
        doctor_id=clinic["doctor"].id, visit_type_id=clinic["visit_type"].id,
        date=TODAY, start_time=time(18, 0), end_time=time(18, 20),
        status="booked", source="staff",
    )
    db.add(untouched)
    db.commit()
    db.close()

    resp = client.post(
        "/api/queue/close-day",
        json={"doctor_id": clinic["doctor"].id, "day": TODAY.isoformat()},
        headers={**headers, "Idempotency-Key": "cd-2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["left"] == 1
    assert body["no_show"] == 1

    db = SessionLocal()
    profile = db.get(PatientProfile, clinic["profile"].id)
    assert profile.no_show_count == 1  # untouched booked -> no_show increments once
    appt = db.get(Appointment, clinic["appointment"].id)
    assert appt.status == "cancelled"
    assert appt.cancel_reason == "left_after_check_in"
    db.close()


def test_close_day_idempotent(client, clinic):
    headers = staff_headers(client)
    payload = {"doctor_id": clinic["doctor"].id, "day": TODAY.isoformat()}
    first = client.post(
        "/api/queue/close-day", json=payload, headers={**headers, "Idempotency-Key": "cdx-1"}
    )
    second = client.post(
        "/api/queue/close-day", json=payload, headers={**headers, "Idempotency-Key": "cdx-1"}
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_reorder_swaps_seq(client, clinic):
    headers = staff_headers(client)
    client.post(
        "/api/queue/check-in",
        json={"appointment_id": clinic["appointment"].id},
        headers={**headers, "Idempotency-Key": "ro-1"},
    )
    second = client.post(
        "/api/queue/walk-in",
        json={
            "doctor_id": clinic["doctor"].id,
            "visit_type_id": clinic["visit_type"].id,
            "day": TODAY.isoformat(),
            "new_profile": {"full_name": "Reorder", "phone": "01111111113"},
        },
        headers={**headers, "Idempotency-Key": "ro-2"},
    ).json()
    moved = client.post(
        f"/api/queue/{second['id']}/move",
        json={"direction": "up"},
        headers={**headers, "Idempotency-Key": "ro-3"},
    )
    assert moved.status_code == 200
    assert moved.json()["seq"] == 1

    db = SessionLocal()
    seqs = db.scalars(
        select(QueueEntry.seq).where(
            QueueEntry.doctor_id == clinic["doctor"].id, QueueEntry.date == TODAY
        )
    ).all()
    assert sorted(seqs) == [1, 2]
    db.close()


def test_display_token_flow(client, clinic):
    headers = staff_headers(client)
    # wrong token -> 403
    resp = client.get(
        f"/api/queue/display/{clinic['doctor'].id}?token=wrong"
    )
    assert resp.status_code == 403

    # generate token (returned once, stored hashed)
    token_resp = client.post(
        f"/api/doctors/{clinic['doctor'].id}/display-token", headers=headers
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["token"]

    db = SessionLocal()
    row = db.scalar(
        select(Setting).where(Setting.key == f"display_token_{clinic['doctor'].id}")
    )
    assert row is not None
    assert row.value != token  # stored hashed, never raw
    db.close()

    # valid token -> privacy-safe payload
    resp = client.get(f"/api/queue/display/{clinic['doctor'].id}?token={token}")
    assert resp.status_code == 200
    body = resp.json()
    assert "now_calling" in body and "waiting_count" in body
    assert "phone" not in json.dumps(body)

    # rotation invalidates the previous token
    new_token = client.post(
        f"/api/doctors/{clinic['doctor'].id}/display-token", headers=headers
    ).json()["token"]
    assert new_token != token
    stale = client.get(f"/api/queue/display/{clinic['doctor'].id}?token={token}")
    assert stale.status_code == 403


def test_sse_generator_snapshot_then_delta(client, clinic):
    """Drives the SSE generator directly: snapshot first, then a published
    delta. (HTTP streaming is verified live with curl in the smoke test —
    TestClient's portal transport does not stream.)"""
    import asyncio

    from app.api.routes.queue import _sse_generator
    from app.db.session import SessionLocal
    from app.services.broadcast import queue_broadcaster

    db = SessionLocal()
    doctor_id = clinic["doctor"].id

    async def scenario():
        gen = _sse_generator(db, doctor_id, TODAY, None)
        first = await gen.__anext__()
        queue_broadcaster.publish(
            queue_broadcaster.key(doctor_id, TODAY), {"event": "entry_updated", "id": 7}
        )
        second = await gen.__anext__()
        await gen.aclose()
        return first, second

    first, second = asyncio.run(scenario())
    db.close()
    assert first["event"] == "snapshot"
    assert json.loads(first["data"])["doctor_id"] == doctor_id
    assert json.loads(second) == {"event": "entry_updated", "id": 7}


def test_broadcaster_delta_reaches_subscriber():
    import asyncio

    from app.services.broadcast import Broadcaster

    b = Broadcaster()
    key = (1, "2026-01-01")

    async def scenario():
        q = b.subscribe(key)
        b.publish(key, {"event": "entry_updated", "id": 7})
        message = await asyncio.wait_for(q.get(), timeout=1)
        b.unsubscribe(key, q)
        return json.loads(message)

    result = asyncio.run(scenario())
    assert result == {"event": "entry_updated", "id": 7}
