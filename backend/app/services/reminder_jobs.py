"""Automated local reminders (Plan/14 C11).

A background job (every 5 minutes, in-process) finds tomorrow's
appointments and:
- sends an SMS via the configured local SMSC gateway (only when
  `reminder.sms_gateway_url` is set), logging each send to the C3
  communication log;
- queues an email reminder through the outbox worker for patients with an
  account email.

Every appointment is only reminded once per channel (marker columns).
"""

import asyncio
import logging
import urllib.parse
import urllib.request
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.identity import PatientAccount, PatientProfile
from app.models.scheduling import Appointment
from app.services.outbox import enqueue
from app.services.settings import get_setting

logger = logging.getLogger("hmsv2.reminders")
INTERVAL_SECONDS = 300


def _tomorrow() -> date:
    return datetime.now(UTC).date() + timedelta(days=1)


def _phone_number(profile: PatientProfile, db: Session) -> str | None:
    country_code = str(get_setting(db, "clinic.country_code", "20") or "20")
    digits = "".join(ch for ch in (profile.phone or "") if ch.isdigit())
    if len(digits) < 8:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = country_code + digits[1:]
    return digits if len(digits) <= 15 else None


def _send_sms(gateway_url: str, token: str, sender: str, to: str, text: str) -> None:
    params = urllib.parse.urlencode({"to": to, "text": text, "sender": sender})
    request = urllib.request.Request(
        f"{gateway_url}?{params}" if "?" not in gateway_url else f"{gateway_url}&{params}",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310 - local SMSC
        resp.read()


def _reminder_text(db: Session, appointment: Appointment, profile: PatientProfile) -> str:
    locale = "ar"
    template = get_setting(db, "reminder.whatsapp_template_ar", "") or get_setting(
        db, "reminder.whatsapp_template_en", ""
    )
    clinic_name = get_setting(db, "clinic.name", {}).get(locale, "") or ""
    clinic_phone = ", ".join(get_setting(db, "clinic.phones", []) or [])
    from app.models.identity import Doctor, StaffUser

    doctor = db.get(Doctor, appointment.doctor_id)
    doctor_name = None
    if doctor:
        user = db.get(StaffUser, doctor.staff_user_id)
        doctor_name = user.full_name if user else None
    time_or_day = appointment.start_time.strftime("%H:%M") if appointment.start_time else ""
    return (
        template
        .replace("{patient_name}", profile.full_name or "")
        .replace("{doctor_name}", doctor_name or "")
        .replace("{date}", appointment.date.isoformat())
        .replace("{time_or_day}", time_or_day)
        .replace("{clinic_name}", clinic_name)
        .replace("{clinic_phone}", clinic_phone)
    )


def run_once() -> dict:
    """One sweep: SMS + email reminders for tomorrow's appointments."""
    result = {"sms": 0, "email": 0}
    with SessionLocal() as db:
        gateway = str(get_setting(db, "reminder.sms_gateway_url", "") or "")
        token = str(get_setting(db, "reminder.sms_token", "") or "")
        sender = str(get_setting(db, "reminder.sms_sender", "") or "")
        appts = db.scalars(
            select(Appointment).where(
                Appointment.date == _tomorrow(),
                Appointment.status.in_(("booked", "checked_in")),
            )
        ).all()
        for appt in appts:
            profile = db.get(PatientProfile, appt.patient_profile_id)
            if profile is None:
                continue
            # SMS via local gateway
            if gateway and appt.reminder_sms_sent_at is None:
                phone = _phone_number(profile, db)
                if phone:
                    try:
                        _send_sms(gateway, token, sender, phone, _reminder_text(db, appt, profile))
                    except Exception as exc:  # noqa: BLE001 - keep sweeping
                        logger.warning("sms reminder failed for %s: %s", appt.booking_ref, exc)
                    else:
                        from app.services.communications import log_communication

                        log_communication(
                            db, patient_profile_id=profile.id, channel="sms",
                            summary=f"Reminder SMS for {appt.date.isoformat()}",
                        )
                        appt.reminder_sms_sent_at = datetime.now(UTC)
                        db.commit()
                        result["sms"] += 1
            # email via outbox worker
            if appt.reminder_email_sent_at is None:
                account = db.get(PatientAccount, profile.account_id) if profile.account_id else None
                if account and account.email and appt.reminder_email_sent_at is None:
                    enqueue(
                        db,
                        kind="email_reminder",
                        aggregate_type="appointment",
                        aggregate_id=appt.id,
                        payload={
                            "to": account.email,
                            "patient_name": profile.full_name or "",
                            "date": appt.date.isoformat(),
                            "time": appt.start_time.strftime("%H:%M") if appt.start_time else "",
                            "booking_ref": appt.booking_ref,
                        },
                        dedupe_key=f"reminder:{appt.booking_ref}",
                    )
                    appt.reminder_email_sent_at = datetime.now(UTC)
                    db.commit()
                    result["email"] += 1
    return result


async def reminder_loop(stop: asyncio.Event) -> None:
    """5-minute sweep; never crashes the process."""
    while not stop.is_set():
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("reminder sweep crashed; continuing")
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL_SECONDS)
