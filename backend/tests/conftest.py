"""Test bootstrap: isolated SQLite databases + app/client fixtures.

Environment must be configured BEFORE any app module import — pytest imports
this file first, so this is safe.
"""

import base64
import os
import secrets
from datetime import date, time

TODAY = date.today()

os.environ["DATABASE_URL"] = "sqlite:///./test_hmsv2.db"
os.environ["AUDIT_DATABASE_URL"] = "sqlite:///./test_hmsv2_audit.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["APP_ENV"] = "test"
os.environ["FIELD_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"k" * 32).decode()
os.environ["AUDIT_CHECKPOINT_DIR"] = "./test_checkpoints"
os.environ["IDEMPOTENCY_TTL_DAYS"] = "7"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.audit.models import AuditBase  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, audit_engine, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.identity import Doctor, PatientProfile, StaffUser  # noqa: E402
from app.models.scheduling import Appointment, DoctorSchedule, VisitType  # noqa: E402
from app.services.roles import role_id as _rid  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _fresh_databases():
    # Drop + recreate both schemas once per session for deterministic tests.
    AuditBase.metadata.drop_all(audit_engine)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    AuditBase.metadata.create_all(audit_engine)
    # Seed the permission catalog + system roles, then bootstrap staff.
    session = SessionLocal()
    from app.services.roles import seed_system_roles

    seed_system_roles(session)

    from app.models.identity import Role, StaffUser

    admin_role = session.scalar(select(Role).where(Role.name == "admin"))
    sec_role = session.scalar(select(Role).where(Role.name == "secretary"))
    session.add(
        StaffUser(
            email="admin@example.com",
            password_hash=hash_password("passw0rd"),
            full_name="Admin",
            role_id=admin_role.id,
            is_active=True,
        )
    )
    session.add(
        StaffUser(
            email="sec@example.com",
            password_hash=hash_password("passw0rd"),
            full_name="Sec",
            role_id=sec_role.id,
            is_active=True,
        )
    )
    from app.models.comms import PrintTemplate
    from app.services.print_templates import PRINT_TEMPLATES

    for key, locales in PRINT_TEMPLATES.items():
        for locale, (title, body) in locales.items():
            session.add(PrintTemplate(key=key, locale=locale, title=title, body_html=body))
    session.commit()
    session.close()
    yield
    Base.metadata.drop_all(engine)
    AuditBase.metadata.drop_all(audit_engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client():
    return TestClient(create_app())


def make_staff(db, *, email, password="passw0rd", role="secretary", is_active=True):

    from app.models.identity import Role, StaffUser

    role_row = db.scalar(select(Role).where(Role.name == role))
    if role_row is None:
        raise RuntimeError(f"role {role} not seeded — run seed or conftest bootstrap")
    user = StaffUser(
        email=email,
        password_hash=hash_password(password),
        full_name=email.split("@")[0],
        role_id=role_row.id,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture(scope="session")
def admin_user():
    from app.models.identity import StaffUser

    session = SessionLocal()
    user = session.query(StaffUser).filter_by(email="admin@example.com").one()
    session.close()
    return user


@pytest.fixture(scope="session")
def secretary_user():
    from app.models.identity import StaffUser

    session = SessionLocal()
    user = session.query(StaffUser).filter_by(email="sec@example.com").one()
    session.close()
    return user


@pytest.fixture()
def clinic(client):
    db = SessionLocal()
    doc_user = StaffUser(
        email=f"fin-{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("passw0rd"), full_name="Fin Doc",
        role_id=_rid(db, "doctor"), is_active=True,
    )
    db.add(doc_user)
    db.flush()
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
    vt = VisitType(name="Consultation", name_ar="كشف", duration_minutes=20, default_price=300)
    db.add(vt)
    db.flush()
    profile = PatientProfile(
        code=f"P-F{secrets.token_hex(4).upper()}", full_name="Fin Patient", phone="010"
    )
    db.add(profile)
    db.flush()
    appt = Appointment(
        booking_ref=f"BK-F{secrets.token_hex(4).upper()}", patient_profile_id=profile.id,
        doctor_id=doctor.id, visit_type_id=vt.id, date=TODAY,
        start_time=time(17, 0), end_time=time(17, 20), status="booked", source="staff",
    )
    db.add(appt)
    db.commit()
    doc_email = doc_user.email
    result = {
        "doctor_id": doctor.id, "doc_email": doc_email, "visit_type_id": vt.id,
        "profile_id": profile.id, "appointment_id": appt.id,
    }
    db.close()

    token = client.post(
        "/api/auth/login", json={"email": doc_email, "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    result["token"] = token
    return result





def csrf_headers(client) -> dict:
    csrf = client.cookies.get("hmsv2_csrf")
    return {"X-CSRF-Token": csrf} if csrf else {}
