"""Scheduling tests (Plan/03 §7): slots, capacity, moves, no-show,
idempotency, concurrency, ownership."""

import threading
from datetime import date, time, timedelta

import pytest

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.identity import Doctor, StaffUser
from app.models.scheduling import DoctorSchedule, VisitType
from app.services.roles import role_id as _rid
from tests.conftest import csrf_headers

TODAY = date.today()


def make_doctor(db, *, mode="slots", day_capacity=None, slot_capacity=1):
    import secrets

    user = StaffUser(
        email=f"dr-{secrets.token_hex(4)}-{mode}@example.com",
        password_hash=hash_password("passw0rd"),
        full_name="Test Doctor",
        role_id=_rid(db, "doctor"),
        is_active=True,
    )
    db.add(user)
    db.flush()
    doctor = Doctor(
        staff_user_id=user.id,
        specialty="Test",
        booking_mode=mode,
        default_slot_minutes=20,
        buffer_minutes=0,
        day_capacity=day_capacity,
        slot_capacity=slot_capacity,
        billing_mode="per_visit",
        is_bookable_online=True,
    )
    db.add(doctor)
    db.flush()
    # Monday..Sunday 17:00-21:00 every day for test simplicity
    for wd in range(7):
        db.add(
            DoctorSchedule(
                doctor_id=doctor.id, weekday=wd, start_time=time(17, 0), end_time=time(21, 0)
            )
        )
    vt = VisitType(
        name="Consultation", name_ar="كشف", duration_minutes=20, default_price=300, is_active=True
    )
    db.add(vt)
    db.commit()
    return doctor, vt


def make_patient(client, email=None):
    import secrets

    email = email or f"pat-{secrets.token_hex(4)}@example.com"
    resp = client.post(
        "/api/public/auth/register",
        json={"full_name": "Patient", "email": email, "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    resp = client.post(
        "/api/public/profiles",
        json={"full_name": "Patient P", "phone": "01000000000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return token, resp.json()["id"]


def admin_headers(client):
    resp1 = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    resp2 = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    assert resp1.status_code == 200, f"login1: {resp1.status_code} {resp1.text}"
    assert resp2.status_code == 200, f"login2: {resp2.status_code} {resp2.text}"
    return {"Authorization": f"Bearer {resp2.json()['access_token']}"}


@pytest.fixture()
def slots_doctor():
    db = SessionLocal()
    doctor, vt = make_doctor(db, mode="slots")
    db.close()
    return doctor.id, vt.id


def test_slots_generation_matches_shift(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    day = TODAY + timedelta(days=7)
    resp = client.get(
        f"/api/availability/{doctor_id}",
        params={"date": day.isoformat(), "visit_type_id": vt_id},
        headers=admin_headers(client),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "slots"
    assert body["reason"] is None
    # 17:00->21:00, len 20, buffer 0 -> 12 slots (17:00 ... 20:40)
    starts = [s["start"] for s in body["slots"]]
    assert starts[0] == "17:00"
    assert starts[-1] == "20:40"
    assert len(starts) == 12


def test_block_removes_date(client, slots_doctor):
    from app.db.session import SessionLocal
    from app.models.scheduling import ScheduleBlock

    doctor_id, vt_id = slots_doctor
    db = SessionLocal()
    db.add(ScheduleBlock(doctor_id=doctor_id, date_from=TODAY, date_to=TODAY + timedelta(days=10)))
    db.commit()
    db.close()
    resp = client.get(
        f"/api/availability/{doctor_id}",
        params={"date": (TODAY + timedelta(days=7)).isoformat(), "visit_type_id": vt_id},
        headers=admin_headers(client),
    )
    assert resp.json()["reason"] == "block"


def test_public_book_and_verify(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    token, profile_id = make_patient(client)
    day = TODAY + timedelta(days=7)
    resp = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day.isoformat(), "start_time": "17:00"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "bk-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["booking_ref"].startswith("BK-")
    assert body["status"] == "booked"
    assert body["start_time"] == "17:00"


def test_public_book_requires_auth(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    resp = client.post(
        "/api/public/appointments",
        json={"profile_id": 1, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": TODAY.isoformat()},
    )
    assert resp.status_code == 401


def test_book_other_profiles_profile_403(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    token, profile_id = make_patient(client, email="other@example.com")
    resp = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id + 999, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": (TODAY + timedelta(days=7)).isoformat(), "start_time": "17:00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_slot_capacity_conflict_and_staff_force(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    token, profile_id = make_patient(client)
    day = TODAY + timedelta(days=7)
    url = "/api/public/appointments"
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "cap-1"}
    first = client.post(
        url,
        json={"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day.isoformat(), "start_time": "17:00"},
        headers=headers,
    )
    assert first.status_code == 200
    second = client.post(
        url,
        json={"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day.isoformat(), "start_time": "17:00"},
        headers={**headers, "Idempotency-Key": "cap-2"},
    )
    assert second.status_code == 409

    # staff can force
    staff = client.post(
        "/api/appointments",
        json={"patient_profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day.isoformat(), "start_time": "17:00", "force": True},
        headers=admin_headers(client),
    )
    assert staff.status_code == 200


def test_idempotent_replay_and_key_reuse(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    token, profile_id = make_patient(client)  # unique random email
    day = TODAY + timedelta(days=7)
    payload = {"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
               "date": day.isoformat(), "start_time": "18:00"}
    first = client.post(
        "/api/public/appointments", json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "same-key"},
    )
    second = client.post(
        "/api/public/appointments", json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "same-key"},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    changed = client.post(
        "/api/public/appointments",
        json={**payload, "start_time": "19:00"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "same-key"},
    )
    assert changed.status_code == 409


def test_day_queue_booking_has_no_time(client):
    db = SessionLocal()
    doctor, vt = make_doctor(db, mode="day_queue", day_capacity=3)
    db.close()
    token, profile_id = make_patient(client, email="dq@example.com")
    day = TODAY + timedelta(days=7)
    resp = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id, "doctor_id": doctor.id, "visit_type_id": vt.id,
              "date": day.isoformat()},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "dq-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["start_time"] is None


def test_move_keeps_booking_ref(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    token, profile_id = make_patient(client, email="move@example.com")
    day = TODAY + timedelta(days=7)
    appt = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day.isoformat(), "start_time": "17:00"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "mv-1"},
    ).json()
    moved = client.post(
        f"/api/public/appointments/{appt['id']}/move",
        json={"date": day.isoformat(), "start_time": "18:00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert moved.status_code == 200
    assert moved.json()["booking_ref"] == appt["booking_ref"]
    assert moved.json()["start_time"] == "18:00"


def test_cancel_and_noshow_rules(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    token, profile_id = make_patient(client, email="cn@example.com")
    day = TODAY + timedelta(days=7)
    appt = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day.isoformat(), "start_time": "17:00"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "cn-1"},
    ).json()

    # patient cancel before check-in
    resp = client.post(
        f"/api/public/appointments/{appt['id']}/cancel",
        json={"reason": "changed my mind"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # cancel twice -> 409
    resp = client.post(
        f"/api/public/appointments/{appt['id']}/cancel", json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_noshow_increments_counter_once(client, slots_doctor):
    doctor_id, vt_id = slots_doctor
    token, profile_id = make_patient(client, email="ns@example.com")
    day = TODAY + timedelta(days=7)
    appt = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day.isoformat(), "start_time": "17:00"},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "ns-1"},
    ).json()
    admin = admin_headers(client)
    first = client.post(f"/api/appointments/{appt['id']}/no-show", headers=admin)
    assert first.status_code == 200
    second = client.post(f"/api/appointments/{appt['id']}/no-show", headers=admin)
    assert second.status_code == 409

    from app.models.identity import PatientProfile

    db = SessionLocal()
    profile = db.get(PatientProfile, profile_id)
    assert profile.no_show_count == 1
    db.close()


def test_day_capacity_reached(client):
    db = SessionLocal()
    doctor, vt = make_doctor(db, mode="day_queue", day_capacity=1)
    db.close()
    token, profile_id = make_patient(client, email="dc@example.com")
    day = TODAY + timedelta(days=7)
    first = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id, "doctor_id": doctor.id, "visit_type_id": vt.id,
              "date": day.isoformat()},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "dc-1"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/public/appointments",
        json={"profile_id": profile_id, "doctor_id": doctor.id, "visit_type_id": vt.id,
              "date": day.isoformat()},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "dc-2"},
    )
    assert second.status_code == 409


def test_concurrent_booking_last_slot(client, slots_doctor):
    """Two simultaneous public bookings for the same slot: exactly one wins."""
    doctor_id, vt_id = slots_doctor
    day = TODAY + timedelta(days=7)
    token_a, profile_a = make_patient(client, email="cc-a@example.com")
    token_b, profile_b = make_patient(client, email="cc-b@example.com")
    results = []

    def book(token, profile_id, key):
        resp = client.post(
            "/api/public/appointments",
            json={"profile_id": profile_id, "doctor_id": doctor_id, "visit_type_id": vt_id,
                  "date": day.isoformat(), "start_time": "17:00"},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        results.append(resp.status_code)

    threads = [
        threading.Thread(target=book, args=(token_a, profile_a, "cc-1")),
        threading.Thread(target=book, args=(token_b, profile_b, "cc-2")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [200, 409]
