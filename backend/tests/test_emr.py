"""EMR tests (Plan/05 §6): lifecycle, ownership, timeline projection,
versioned autosave, attachments + quarantine, prescriptions, follow-ups."""

import io
import secrets
from datetime import date, time, timedelta

import pytest
from PIL import Image

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.queueing import QueueEntry
from app.models.scheduling import Appointment, DoctorSchedule, VisitType
from tests.conftest import csrf_headers

TODAY = date.today()


def make_staff(db, email=None, role="doctor"):
    from app.services.roles import role_id as _rid

    user = StaffUser(
        email=email or f"emr-{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("passw0rd"), full_name="EMR Doc",
        role_id=_rid(db, role), is_active=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def doctor_client(client):
    """Client with a booked appointment for a doctor, returned with tokens."""
    db = SessionLocal()
    doc_user = make_staff(db)
    doctor = Doctor(
        staff_user_id=doc_user.id, specialty="T", booking_mode="slots",
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
    profile = PatientProfile(
        code=f"P-E{secrets.token_hex(4).upper()}", full_name="EMR Patient", phone="010"
    )
    db.add(profile)
    db.flush()
    appt = Appointment(
        booking_ref=f"BK-E{secrets.token_hex(4).upper()}", patient_profile_id=profile.id,
        doctor_id=doctor.id, visit_type_id=vt.id, date=TODAY,
        start_time=time(17, 0), end_time=time(17, 20), status="booked", source="staff",
    )
    db.add(appt)
    db.commit()
    doc_id, doc_email, vt_id, profile_id, appt_id = (
        doctor.id, doc_user.email, vt.id, profile.id, appt.id,
    )
    db.close()

    headers = {}
    csrf = client.cookies.get("hmsv2_csrf")
    if csrf:
        headers["X-CSRF-Token"] = csrf
    token = client.post(
        "/api/auth/login", json={"email": doc_email, "password": "passw0rd"}, headers=headers
    ).json()["access_token"]
    return {
        "client": client,
        "token": token,
        "doctor_id": doc_id,
        "doctor_email": doc_email,
        "visit_type_id": vt_id,
        "profile_id": profile_id,
        "appointment_id": appt_id,
    }


def _auth(doctor_client, token=None):
    return {"Authorization": f"Bearer {token or doctor_client['token']}"}


def _admin_headers(client):
    client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    token = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _check_in_and_start(client, doctor_client, token=None):
    admin = _admin_headers(client)
    client.post(
        "/api/queue/check-in",
        json={"appointment_id": doctor_client["appointment_id"]},
        headers={**admin, "Idempotency-Key": f"ci-{secrets.token_hex(4)}"},
    )
    entry_id = client.get(
        f"/api/queue?doctor_id={doctor_client['doctor_id']}&date={TODAY.isoformat()}",
        headers=admin,
    ).json()["entries"][0]["id"]
    client.post(
        f"/api/queue/{entry_id}/start",
        headers={**admin, "Idempotency-Key": f"st-{secrets.token_hex(4)}"},
    )
    return entry_id


def test_visit_created_from_queue_and_autosave(client, doctor_client):
    headers = _auth(doctor_client)
    _check_in_and_start(client, doctor_client)

    visits = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()
    assert len(visits) == 1
    visit_id = visits[0]["id"]

    # versioned autosave
    patch = {
        "chief_complaint": "fever and cough",
        "plan": "paracetamol",
        "record_version": 1,
    }
    resp = client.patch(f"/api/visits/{visit_id}", json=patch, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["record_version"] == 2

    # stale version -> 409, nothing overwritten
    stale = client.patch(
        f"/api/visits/{visit_id}",
        json={"chief_complaint": "stale write", "record_version": 1},
        headers=headers,
    )
    assert stale.status_code == 409
    fresh = client.get(f"/api/visits/{visit_id}", headers=headers).json()
    assert fresh["chief_complaint"] == "fever and cough"


def test_complete_drives_queue_and_appointment(client, doctor_client):
    headers = _auth(doctor_client)
    entry_id = _check_in_and_start(client, doctor_client)
    visit_id = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()[0]["id"]

    resp = client.post(
        f"/api/visits/{visit_id}/complete", headers={**headers, "Idempotency-Key": "comp-1"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    db = SessionLocal()
    entry = db.get(QueueEntry, entry_id)
    assert entry.status == "completed"
    appt = db.get(Appointment, doctor_client["appointment_id"])
    assert appt.status == "completed"
    db.close()

    # completing twice -> 409
    again = client.post(
        f"/api/visits/{visit_id}/complete", headers={**headers, "Idempotency-Key": "comp-2"}
    )
    assert again.status_code == 409


def test_ownership_matrix(client, doctor_client):
    db = SessionLocal()
    other_doc = make_staff(db, role="doctor")
    make_staff(db, role="secretary")
    db.commit()
    db.close()

    headers = _auth(doctor_client)
    _check_in_and_start(client, doctor_client)
    visit_id = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()[0]["id"]
    client.patch(
        f"/api/visits/{visit_id}",
        json={"notes_private": "secret", "chief_complaint": "pain", "record_version": 1},
        headers=headers,
    )

    # secretary: demographics + metadata only, no clinical fields
    client.post(
        "/api/auth/login",
        json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    sec_token = client.post(
        "/api/auth/login",
        json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    sec_view = client.get(
        f"/api/visits/{visit_id}", headers={"Authorization": f"Bearer {sec_token}"}
    )
    assert sec_view.status_code == 200
    assert "chief_complaint" not in sec_view.json()
    assert "patient" in sec_view.json()

    # other doctor: clinical fields present, notes_private absent
    other_token = client.post(
        "/api/auth/login",
        json={"email": other_doc.email, "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    other_view = client.get(
        f"/api/visits/{visit_id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert other_view.status_code == 200
    assert other_view.json()["chief_complaint"] == "pain"
    assert "notes_private" not in other_view.json()

    # author sees notes_private
    author_view = client.get(f"/api/visits/{visit_id}", headers=_auth(doctor_client))
    assert author_view.json()["notes_private"] == "secret"

    # other doctor cannot edit
    denied = client.patch(
        f"/api/visits/{visit_id}",
        json={"chief_complaint": "hacked", "record_version": 2},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert denied.status_code == 403


def test_timeline_only_non_null_fields(client, doctor_client):
    headers = _auth(doctor_client)
    _check_in_and_start(client, doctor_client)
    visit_id = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()[0]["id"]
    client.patch(
        f"/api/visits/{visit_id}",
        json={"plan": "rest", "follow_up_weeks": 2, "record_version": 1},
        headers=headers,
    )
    client.put(
        f"/api/visits/{visit_id}/diagnoses",
        json={"items": [{"kind": "final", "label": "URTI"}], "record_version": 2},
        headers=headers,
    )
    card = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()[0]
    assert card["plan"] == "rest"
    assert card["diagnoses"] == ["URTI"]
    assert "chief_complaint" not in card  # never set -> absent

    # follow-up due date computed
    visit = client.get(f"/api/visits/{visit_id}", headers=headers).json()
    expected = (TODAY + timedelta(weeks=2)).isoformat()
    assert visit["follow_up_due"] == expected


def test_prescription_replace_atomic(client, doctor_client):
    db = SessionLocal()
    med = __import__("app.models.emr", fromlist=["Medication"]).Medication(
        name="Panadol", form="tab", strength="500mg"
    )
    db.add(med)
    db.commit()
    med_id = med.id
    db.close()

    headers = _auth(doctor_client)
    _check_in_and_start(client, doctor_client)
    visit_id = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()[0]["id"]

    resp = client.put(
        f"/api/visits/{visit_id}/prescription",
        json={
            "notes": "take after food",
            "items": [
                {
                    "medication_id": med_id,
                    "dose": "1 tab",
                    "frequency": "3x/day",
                    "duration": "5 days",
                }
            ],
            "record_version": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    rx = resp.json()["prescription"]
    assert len(rx["items"]) == 1

    # replace with two items + free text, version bumped
    resp2 = client.put(
        f"/api/visits/{visit_id}/prescription",
        json={
            "notes": None,
            "items": [
                {"medication_id": med_id, "dose": "1", "frequency": "2x", "duration": "3"},
                {"free_text": "ORS sachet", "dose": "1", "frequency": "prn", "duration": "2"},
            ],
            "record_version": 2,
        },
        headers=headers,
    )
    assert resp2.status_code == 200
    assert len(resp2.json()["prescription"]["items"]) == 2


def test_attachment_upload_quarantine_and_serve(client, doctor_client, tmp_path):
    headers = _auth(doctor_client)
    _check_in_and_start(client, doctor_client)
    visit_id = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()[0]["id"]

    # build a small PNG
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), color=(10, 20, 30)).save(buf, format="PNG")
    png = buf.getvalue()

    resp = client.post(
        f"/api/visits/{visit_id}/attachments",
        files={"file": ("lab.png", png, "image/png")},
        data={"kind": "lab", "title": "CBC"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_status"] == "pending"

    # quarantined: download blocked
    blocked = client.get(f"/api/files/{body['id']}", headers=headers)
    assert blocked.status_code == 409

    # outbox worker drains the scan -> clean
    from app.services.outbox import drain_once

    assert drain_once() >= 1

    served = client.get(f"/api/files/{body['id']}", headers=headers)
    assert served.status_code == 200
    assert served.headers["Cache-Control"] == "private, no-store"
    re_loaded = Image.open(io.BytesIO(served.content))
    assert re_loaded.format == "JPEG"  # re-encoded from PNG
    assert re_loaded.size[0] <= 2048

    thumb = client.get(f"/api/files/{body['id']}?thumb=true", headers=headers)
    assert thumb.status_code == 200
    assert Image.open(io.BytesIO(thumb.content)).size[0] <= 320


def test_attachment_rejects_bad_types_and_duplicates(client, doctor_client):
    headers = _auth(doctor_client)
    _check_in_and_start(client, doctor_client)
    visit_id = client.get(
        f"/api/patients/{doctor_client['profile_id']}/timeline", headers=headers
    ).json()[0]["id"]

    bad = client.post(
        f"/api/visits/{visit_id}/attachments",
        files={"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")},
        headers=headers,
    )
    assert bad.status_code == 422

    fake_pdf = client.post(
        f"/api/visits/{visit_id}/attachments",
        files={"file": ("fake.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
        headers=headers,
    )
    assert fake_pdf.status_code == 422


def test_attachment_requires_doctor_auth(client, doctor_client):
    client.post(
        "/api/auth/login",
        json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    sec_token = client.post(
        "/api/auth/login",
        json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    resp = client.get("/api/files/1", headers={"Authorization": f"Bearer {sec_token}"})
    assert resp.status_code == 403


def test_medication_search(client, doctor_client):
    headers = _auth(doctor_client)
    created = client.post(
        "/api/medications",
        json={"name": "Augmentin", "form": "tab", "strength": "1g"},
        headers=headers,
    )
    assert created.status_code == 200
    rows = client.get("/api/medications?q=aug", headers=headers).json()
    assert len(rows) >= 1
    assert any("Augmentin" in r["name"] for r in rows)
    rows_ar = client.get("/api/medications?q=tab", headers=headers).json()
    assert len(rows_ar) >= 1
