"""Printing / recall / search tests (Plan/07 §6)."""

import secrets
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.emr import Visit
from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.scheduling import VisitType
from tests.conftest import csrf_headers

TODAY = date.today()


@pytest.fixture()
def emr_setup(client):
    """Doctor + visit type + a patient with a completed visit (no queue)."""
    db = SessionLocal()
    doc_user = StaffUser(
        email=f"pr-{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("passw0rd"), full_name="Print Doc",
        role="doctor", is_active=True,
    )
    db.add(doc_user)
    db.flush()
    doctor = Doctor(
        staff_user_id=doc_user.id, specialty="General", billing_mode="per_visit"
    )
    db.add(doctor)
    db.flush()
    vt = VisitType(name="Consultation", name_ar="كشف", duration_minutes=20, default_price=300)
    db.add(vt)
    db.flush()
    profile = PatientProfile(
        code=f"P-R{secrets.token_hex(4).upper()}", full_name="Recall Patient", phone="010"
    )
    db.add(profile)
    db.flush()
    visit = Visit(
        patient_profile_id=profile.id, doctor_id=doctor.id, visit_type_id=vt.id,
        status="completed", chief_complaint="follow up needed", follow_up_due=TODAY,
        record_version=1,
    )
    db.add(visit)
    db.commit()
    doc_email = doc_user.email
    result = {"doctor_id": doctor.id, "doc_email": doc_email, "visit_type_id": vt.id,
              "profile_id": profile.id, "visit_id": visit.id}
    db.close()

    token = client.post(
        "/api/auth/login", json={"email": doc_email, "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    result["token"] = token
    return result


def test_recall_list_and_dismiss(client, emr_setup):
    resp = client.get("/api/recalls", headers={"Authorization": f"Bearer {emr_setup['token']}"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["patient_profile_id"] == emr_setup["profile_id"]
    assert row["days_overdue"] == 0
    assert row["no_show_count"] == 0

    # dismiss snoozes the recall
    dismissed = client.post(
        f"/api/recalls/{emr_setup['visit_id']}/dismiss?days=30",
        headers={"Authorization": f"Bearer {emr_setup['token']}"},
    )
    assert dismissed.status_code == 200
    rows = client.get(
        "/api/recalls", headers={"Authorization": f"Bearer {emr_setup['token']}"}
    ).json()
    assert rows == []


def test_recall_hides_booked_patients(client, emr_setup):
    from datetime import time

    from app.models.scheduling import Appointment

    db = SessionLocal()
    db.add(
        Appointment(
            booking_ref=f"BK-R{secrets.token_hex(4).upper()}",
            patient_profile_id=emr_setup["profile_id"], doctor_id=emr_setup["doctor_id"],
            visit_type_id=emr_setup["visit_type_id"], date=TODAY + timedelta(days=1),
            start_time=time(17, 0), status="booked", source="staff",
        )
    )
    db.commit()
    db.close()
    rows = client.get(
        "/api/recalls", headers={"Authorization": f"Bearer {emr_setup['token']}"}
    ).json()
    assert rows == []


def test_patient_search_ranked_and_clean(client, emr_setup):
    headers = {"Authorization": f"Bearer {emr_setup['token']}"}
    # by code prefix
    db = SessionLocal()
    profile = db.get(PatientProfile, emr_setup["profile_id"])
    code = profile.code
    db.close()
    by_code = client.get(f"/api/search/patients?q={code}", headers=headers).json()
    assert by_code["results"][0]["id"] == emr_setup["profile_id"]
    # clinical fields absent
    assert "allergies" not in by_code["results"][0]
    # by name substring
    by_name = client.get("/api/search/patients?q=Recall", headers=headers).json()
    assert any(r["id"] == emr_setup["profile_id"] for r in by_name["results"])


def test_print_token_and_render(client, emr_setup):
    headers = {"Authorization": f"Bearer {emr_setup['token']}"}
    token_resp = client.post(
        f"/api/print/token?key=rx&entity_id={emr_setup['visit_id']}", headers=headers
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["token"]

    page = client.get(
        f"/api/print/rx/{emr_setup['visit_id']}?token={token}&locale=ar"
    )
    assert page.status_code == 200
    html = page.text
    assert "Print Doc" in html
    assert 'dir="rtl"' in html
    assert "Recall Patient" in html
    assert "window.print" in html  # auto-print helper is expected
    assert "<script>alert" not in html  # no injected scripts from templates

    # token is bound to the entity
    other = client.get(
        f"/api/print/rx/{emr_setup['visit_id'] + 999}?token={token}&locale=ar"
    )
    assert other.status_code == 403


def test_secretary_print_restricted(client, emr_setup):
    sec_token = client.post(
        "/api/auth/login", json={"email": "sec@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    sec = {"Authorization": f"Bearer {sec_token}"}
    # rx allowed
    rx = client.post(
        f"/api/print/token?key=rx&entity_id={emr_setup['visit_id']}", headers=sec
    )
    assert rx.status_code == 200
    # report composition denied for secretaries
    report = client.post(
        f"/api/print/token?key=report&entity_id={emr_setup['visit_id']}", headers=sec
    )
    assert report.status_code == 403


def test_template_editor_sanitizes(client, emr_setup):
    from app.models.comms import PrintTemplate

    db = SessionLocal()
    template = db.scalar(select(PrintTemplate).where(PrintTemplate.key == "rx", PrintTemplate.locale == "en"))
    template_id = template.id
    db.close()
    admin = {"Authorization": "Bearer " + _admin_token(client)}

    evil = client.put(
        f"/api/print-templates/{template_id}",
        json={"body_html": "<script>alert(1)</script>${patient.name}"},
        headers=admin,
    )
    assert evil.status_code == 422

    unknown = client.put(
        f"/api/print-templates/{template_id}",
        json={"body_html": "<p>${bogus.placeholder}</p>"},
        headers=admin,
    )
    assert unknown.status_code == 422

    ok = client.put(
        f"/api/print-templates/{template_id}",
        json={"body_html": "<p>Hello ${patient.name}</p>"},
        headers=admin,
    )
    assert ok.status_code == 200


def _admin_token(client):
    client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    token = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    return token
