"""Clinic settings + timezone helpers (Plan/03 R6, conventions)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.config import Setting


def get_setting(db: Session, key: str, default=None):
    row = db.scalar(select(Setting).where(Setting.key == key))
    return row.value if row is not None else default


def clinic_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().CLINIC_TZ)


def clinic_now() -> datetime:
    return datetime.now(clinic_timezone())


def clinic_today() -> date:
    return clinic_now().date()


def booking_horizon_days(db: Session) -> int:
    return int(get_setting(db, "booking.horizon_days", 30))
