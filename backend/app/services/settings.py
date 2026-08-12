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


DEFAULT_SETTINGS = {
    "clinic.name": {"en": "My Clinic", "ar": "عيادتي"},
    "clinic.address": {"en": "", "ar": ""},
    "clinic.phones": [],
    "clinic.country_code": "20",
    "clinic.timezone": "Africa/Cairo",
    "clinic.hours_text": {"en": "", "ar": ""},
    "clinic.location_url": "",
    "billing.currency": "EGP",
    "billing.discount_cap_secretary_pct": 10,
    "billing.cashier_can_adjust_pricing": False,
    "billing.vat_rate_pct": 0,
    "billing.vat_inclusive": True,
    "billing.vat_number": "",
    "billing.vat_exempt": False,
    "booking.horizon_days": 30,
    "reminder.sms_gateway_url": "",
    "reminder.sms_token": "",
    "reminder.sms_sender": "",
    "petty_cash.opening_balance": 0,
    "petty_cash.categories": ["office", "medical", "transport", "staff", "other"],
    "reminder.whatsapp_template_ar": (
        "أهلاً {patient_name}، معاك عيادة {clinic_name}. بنفتكرك بموعدك مع "
        "د. {doctor_name} يوم {date} {time_or_day}. لو محتاج تلغي أو تغيّر "
        "الموعد كلمنا على {clinic_phone}."
    ),
    "reminder.whatsapp_template_en": (
        "Hello {patient_name}, this is {clinic_name} reminding you of your "
        "appointment with Dr. {doctor_name} on {date} {time_or_day}. To "
        "reschedule or cancel, call {clinic_phone}."
    ),
    "public.about": {"en": "", "ar": ""},
    "public.services": {"en": [], "ar": []},
}

