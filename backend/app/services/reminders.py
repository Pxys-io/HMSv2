"""WhatsApp one-click reminders (Plan/08 W1–W4): wa.me deep links with
prefilled messages; no delivery claim, generation only."""

import re
from datetime import date, timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import Doctor, PatientProfile, StaffUser
from app.models.scheduling import Appointment
from app.services.settings import get_setting


def _normalize_phone(phone: str, country_code: str) -> str | None:
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = country_code + digits[1:]
    if len(digits) < 8 or len(digits) > 15:
        return None
    return digits


def reminder_link(db: Session, appointment: Appointment, locale: str) -> dict:
    settings_ctx = {
        "clinic.name": get_setting(db, "clinic.name", {}).get(locale, "") or "",
        "clinic.phone": ", ".join(get_setting(db, "clinic.phones", []) or []),
    }
    template_key = f"reminder.whatsapp_template_{locale}"
    template = get_setting(db, template_key, "") or get_setting(
        db, "reminder.whatsapp_template_en", ""
    )
    profile = db.get(PatientProfile, appointment.patient_profile_id)
    doctor = db.get(Doctor, appointment.doctor_id)
    doctor_name = None
    if doctor:
        user = db.get(StaffUser, doctor.staff_user_id)
        doctor_name = user.full_name if user else None
    country_code = get_setting(db, "clinic.country_code", "20")
    phone = _normalize_phone(profile.phone if profile else "", country_code)
    if phone is None:
        return {"url": None, "reason": "unusable_phone"}

    time_or_day = appointment.start_time.strftime("%H:%M") if appointment.start_time else ""
    message = (
        template.replace("{patient_name}", profile.full_name if profile else "")
        .replace("{doctor_name}", doctor_name or "")
        .replace("{date}", appointment.date.isoformat())
        .replace("{time_or_day}", time_or_day)
        .replace("{clinic_name}", settings_ctx["clinic.name"])
        .replace("{clinic_phone}", settings_ctx["clinic.phone"])
    )
    return {"url": f"https://wa.me/{phone}?text={quote(message)}", "reason": None}


def upcoming_reminders(db: Session, doctor_id: int | None = None, locale: str = "ar") -> list[dict]:
    today = date.today()
    horizon = today + timedelta(days=2)
    stmt = select(Appointment).where(
        Appointment.date >= today,
        Appointment.date <= horizon,
        Appointment.status.in_(("booked", "checked_in")),
    ).order_by(Appointment.date, Appointment.start_time)
    if doctor_id is not None:
        stmt = stmt.where(Appointment.doctor_id == doctor_id)
    rows = db.scalars(stmt).all()
    out = []
    for appointment in rows:
        link = reminder_link(db, appointment, locale)
        profile = db.get(PatientProfile, appointment.patient_profile_id)
        out.append(
            {
                "appointment_id": appointment.id,
                "booking_ref": appointment.booking_ref,
                "patient_name": profile.full_name if profile else None,
                "date": appointment.date.isoformat(),
                "start_time": (
                    appointment.start_time.strftime("%H:%M")
                    if appointment.start_time
                    else None
                ),
                "url": link["url"],
                "link_reason": link["reason"],
                "link_generated_at": appointment.reminder_link_generated_at.isoformat()
                if appointment.reminder_link_generated_at
                else None,
            }
        )
    return out
