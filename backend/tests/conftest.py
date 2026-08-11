"""Test bootstrap: isolated SQLite databases + app/client fixtures.

Environment must be configured BEFORE any app module import — pytest imports
this file first, so this is safe.
"""

import base64
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_hmsv2.db"
os.environ["AUDIT_DATABASE_URL"] = "sqlite:///./test_hmsv2_audit.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["APP_ENV"] = "test"
os.environ["FIELD_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"k" * 32).decode()
os.environ["AUDIT_CHECKPOINT_DIR"] = "./test_checkpoints"
os.environ["IDEMPOTENCY_TTL_DAYS"] = "7"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.audit.models import AuditBase  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, audit_engine, engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _fresh_databases():
    # Drop + recreate both schemas once per session for deterministic tests.
    AuditBase.metadata.drop_all(audit_engine)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    AuditBase.metadata.create_all(audit_engine)
    # Bootstrap staff accounts used across test files (admin/secretary).
    session = SessionLocal()
    from app.models.identity import StaffUser

    session.add(
        StaffUser(
            email="admin@example.com",
            password_hash=hash_password("passw0rd"),
            full_name="Admin",
            role="admin",
            is_active=True,
        )
    )
    session.add(
        StaffUser(
            email="sec@example.com",
            password_hash=hash_password("passw0rd"),
            full_name="Sec",
            role="secretary",
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
    from app.models.identity import StaffUser

    user = StaffUser(
        email=email,
        password_hash=hash_password(password),
        full_name=email.split("@")[0],
        role=role,
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


def csrf_headers(client) -> dict:
    csrf = client.cookies.get("hmsv2_csrf")
    return {"X-CSRF-Token": csrf} if csrf else {}
