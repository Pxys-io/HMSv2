"""Engine and session management for both databases.

Main and audit sessions are always separate transactions. Audit writes must
survive main rollbacks, and audit failures must never be silently swallowed.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
_audit_connect_args = (
    {"check_same_thread": False} if settings.AUDIT_DATABASE_URL.startswith("sqlite") else {}
)


def _tune_sqlite(sqlite_engine) -> None:
    """Dev/test only: this hardware fsyncs SQLite ~200ms per commit; the
    suite performs thousands. Production runs PostgreSQL where this is
    irrelevant, so the pragmas never touch prod semantics."""

    @event.listens_for(sqlite_engine, "connect")
    def _set_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=MEMORY")
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.close()


if settings.APP_ENV in ("dev", "test") and settings.DATABASE_URL.startswith("sqlite"):
    _tune_sqlite(
        engine := create_engine(settings.DATABASE_URL, connect_args=_connect_args, future=True)
    )
else:
    engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

if settings.APP_ENV in ("dev", "test") and settings.AUDIT_DATABASE_URL.startswith("sqlite"):
    _tune_sqlite(
        audit_engine := create_engine(
            settings.AUDIT_DATABASE_URL, connect_args=_audit_connect_args, future=True
        )
    )
else:
    audit_engine = create_engine(
        settings.AUDIT_DATABASE_URL, connect_args=_audit_connect_args, future=True
    )
AuditSessionLocal = sessionmaker(
    bind=audit_engine, autoflush=False, expire_on_commit=False, future=True
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_audit_db() -> Generator[Session, None, None]:
    db = AuditSessionLocal()
    try:
        yield db
    finally:
        db.close()
