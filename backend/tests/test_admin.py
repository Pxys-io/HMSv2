"""Admin workspace backend tests: doctor edit/delete, schedule validation,
role auto-create, settings, public assets, branding."""

import io
import secrets
from datetime import date, time, timedelta

from PIL import Image
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.scheduling import Appointment, DoctorSchedule
from tests.conftest import csrf_headers


def admin_headers(client):
    client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    token = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_doctor_row(db, suffix):
    user = StaffUser(
        email=f"dr-{suffix}@example.com", password_hash="x", full_name="Doc",
        role="doctor", is_active=True,
    )
    db.add(user)
    db.flush()
    doctor = Doctor(staff_user_id=user.id, specialty="General", billing_mode="per_visit")
    db.add(doctor)
    db.commit()
    return doctor


def test_doctor_edit_validations(client):
    headers = admin_headers(client)
    db = SessionLocal()
    doctor = make_doctor_row(db, secrets.token_hex(4))
    doctor_id = doctor.id
    db.close()

    # per_hour without rate -> 422
    resp = client.patch(
        f"/api/doctors/{doctor_id}",
        json={"billing_mode": "per_hour"},
        headers=headers,
    )
    assert resp.status_code == 422

    # per_hour with rate -> ok
    resp = client.patch(
        f"/api/doctors/{doctor_id}",
        json={"billing_mode": "per_hour", "hourly_rate": 500},
        headers=headers,
    )
    assert resp.status_code == 200

    # slots with tiny slot -> 422
    resp = client.patch(
        f"/api/doctors/{doctor_id}",
        json={"booking_mode": "slots", "default_slot_minutes": 2},
        headers=headers,
    )
    assert resp.status_code == 422


def test_doctor_edit_identity_and_warnings(client):
    headers = admin_headers(client)
    db = SessionLocal()
    doctor = make_doctor_row(db, secrets.token_hex(4))
    doctor_id = doctor.id
    db.close()

    # rename + email via the doctor endpoint (single audited action)
    resp = client.patch(
        f"/api/doctors/{doctor_id}",
        json={"full_name": "Renamed Doc", "email": f"renamed-{secrets.token_hex(4)}@example.com"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Renamed Doc"

    # mode switch with a future booking -> 200 + warning
    db = SessionLocal()
    profile = PatientProfile(code=f"P-W{secrets.token_hex(4).upper()}", full_name="P", phone="010")
    db.add(profile)
    db.flush()
    db.add(
        Appointment(
            booking_ref=f"BK-W{secrets.token_hex(4).upper()}", patient_profile_id=profile.id,
            doctor_id=doctor_id, visit_type_id=1, date=date.today() + timedelta(days=7),
            start_time=time(17, 0), status="booked", source="staff",
        )
    )
    db.commit()
    db.close()
    resp = client.patch(
        f"/api/doctors/{doctor_id}", json={"booking_mode": "day_queue"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["warnings"], "expected a warning for the mode switch"


def test_schedule_update_validation(client):
    headers = admin_headers(client)
    db = SessionLocal()
    doctor = make_doctor_row(db, secrets.token_hex(4))
    sched = DoctorSchedule(
        doctor_id=doctor.id, weekday=0, start_time=time(17, 0), end_time=time(21, 0)
    )
    db.add(sched)
    db.commit()
    sched_id = sched.id
    db.close()

    ok = client.patch(f"/api/schedules/{sched_id}", json={"start_time": "18:00"}, headers=headers)
    assert ok.status_code == 200

    inverted = client.patch(
        f"/api/schedules/{sched_id}",
        json={"start_time": "22:00", "end_time": "09:00"},
        headers=headers,
    )
    assert inverted.status_code == 422


def test_role_doctor_auto_creates_profile(client):
    headers = admin_headers(client)
    email = f"autodoc-{secrets.token_hex(4)}@example.com"
    resp = client.post(
        "/api/users",
        json={"email": email, "password": "passw0rd", "full_name": "Auto Doc", "role": "doctor"},
        headers=headers,
    )
    assert resp.status_code == 200
    db = SessionLocal()
    user = db.scalar(select(StaffUser).where(StaffUser.email == email))
    doctor = db.scalar(select(Doctor).where(Doctor.staff_user_id == user.id))
    assert doctor is not None and doctor.specialty == "General"
    db.close()

    # role away from doctor with schedules -> 409
    sched = DoctorSchedule(
        doctor_id=doctor.id, weekday=0, start_time=time(17, 0), end_time=time(21, 0)
    )
    db = SessionLocal()
    db.add(sched)
    db.commit()
    db.close()
    denied = client.patch(
        f"/api/users/{user.id}",
        json={"role": "secretary"},
        headers=headers,
    )
    assert denied.status_code == 409


def test_doctor_deactivate(client):
    headers = admin_headers(client)
    db = SessionLocal()
    doctor = make_doctor_row(db, secrets.token_hex(4))
    doctor_id = doctor.id
    db.close()

    resp = client.delete(f"/api/doctors/{doctor_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["deactivated"] is True

    db = SessionLocal()
    user = db.get(StaffUser, doctor.staff_user_id)
    assert user.is_active is False
    db.close()


def test_doctor_deactivate_blocked_with_future_appointment(client):
    headers = admin_headers(client)
    db = SessionLocal()
    doctor = make_doctor_row(db, secrets.token_hex(4))
    profile = PatientProfile(code=f"P-B{secrets.token_hex(4).upper()}", full_name="P", phone="010")
    db.add(profile)
    db.flush()
    db.add(
        Appointment(
            booking_ref=f"BK-B{secrets.token_hex(4).upper()}", patient_profile_id=profile.id,
            doctor_id=doctor.id, visit_type_id=1, date=date.today() + timedelta(days=3),
            start_time=time(17, 0), status="booked", source="staff",
        )
    )
    db.commit()
    doctor_id = doctor.id
    db.close()

    resp = client.delete(f"/api/doctors/{doctor_id}", headers=headers)
    assert resp.status_code == 409


def test_settings_get_put_and_branding(client):
    headers = admin_headers(client)
    resp = client.get("/api/settings", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "clinic.name" in body
    assert body["booking.horizon_days"] == 30

    updated = client.put(
        "/api/settings",
        json={"clinic.name": {"en": "Bright Clinic", "ar": "عيادة النور"},
              "billing.discount_cap_secretary_pct": 15},
        headers=headers,
    )
    assert updated.status_code == 200

    # unknown key -> 422
    bad = client.put("/api/settings", json={"clinic.bogus": 1}, headers=headers)
    assert bad.status_code == 422

    # branding reflects the change (no auth)
    branding = client.get("/api/public/branding").json()
    assert branding["name"]["en"] == "Bright Clinic"
    assert branding["name"]["ar"] == "عيادة النور"

    # restore defaults so other tests are not affected by shared settings
    client.put(
        "/api/settings",
        json={"clinic.name": {"en": "My Clinic", "ar": "عيادتي"},
              "billing.discount_cap_secretary_pct": 10},
        headers=headers,
    )


def test_public_asset_upload_and_read(client):
    headers = admin_headers(client)
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (10, 200, 100)).save(buf, format="PNG")
    resp = client.post(
        "/api/public-assets?kind=clinic_logo",
        files={"file": ("logo.png", buf.getvalue(), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 200
    asset_id = resp.json()["id"]

    fetched = client.get(f"/api/public/assets/{asset_id}")
    assert fetched.status_code == 200
    assert fetched.headers["Cache-Control"].startswith("public")
    assert Image.open(io.BytesIO(fetched.content)).format == "JPEG"
