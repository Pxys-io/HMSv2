"""Email service (Plan/08 N3): rendered HTML confirmations sent via SMTP;
the outbox worker drives delivery with retries."""

import logging
import re
from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings

logger = logging.getLogger("hmsv2.email")


def render_confirmation(
    *,
    clinic_name: str,
    patient_name: str,
    doctor_name: str,
    date_text: str,
    time_text: str,
    booking_ref: str,
    locale: str,
) -> tuple[str, str]:
    """Returns (subject, html_body). No clinical content ever (N3)."""
    if locale == "ar":
        subject = f"تأكيد حجز موعد — {clinic_name}"
        body = f"""
        <div style="font-family:sans-serif;max-width:560px;margin:auto">
          <h2 style="color:#0d9488">{clinic_name}</h2>
          <p>أهلاً {patient_name}،</p>
          <p>تم تأكيد موعدك مع د. {doctor_name} يوم {date_text} الساعة {time_text}.</p>
          <p>رقم الحجز: <b dir="ltr">{booking_ref}</b></p>
          <p>لإلغاء أو تعديل الموعد، يمكنك الدخول إلى حسابك على الموقع.</p>
        </div>"""
    else:
        subject = f"Appointment confirmed — {clinic_name}"
        body = f"""
        <div style="font-family:sans-serif;max-width:560px;margin:auto">
          <h2 style="color:#0d9488">{clinic_name}</h2>
          <p>Hello {patient_name},</p>
          <p>Your appointment with Dr. {doctor_name} is confirmed
          for {date_text} at {time_text}.</p>
          <p>Booking reference: <b dir="ltr">{booking_ref}</b></p>
          <p>To cancel or reschedule, sign in to your account on our website.</p>
        </div>"""
    return subject, body


async def send_email(to: str, subject: str, html: str) -> None:
    settings = get_settings()
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — would send to %s: %s", to, subject)
        return
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM or "noreply@hmsv2.local"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(re.sub(r"<[^>]+>", "", html))
    message.add_alternative(html, subtype="html")
    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER or None,
        password=settings.SMTP_PASS or None,
        start_tls=bool(settings.SMTP_USER),
    )


def render_reminder(
    patient_name: str, date_text: str, time_text: str, booking_ref: str
) -> tuple[str, str]:
    subject = f"Appointment reminder ({booking_ref})"
    html = (
        "<p>Hello,</p>"
        f"<p>This is a reminder that your appointment is scheduled for "
        f"<b>{date_text}</b> at <b>{time_text}</b>.</p>"
        "<p>To reschedule or cancel, please contact the clinic.</p>"
    )
    return subject, html


def send_reminder_sync(
    to: str, booking_ref: str, date_text: str, time_text: str | None, patient_name: str | None
) -> None:
    subject, html = render_reminder(patient_name or "", date_text, time_text or "", booking_ref)
    send_confirmation_sync(to, subject, html)


def send_confirmation_sync(to: str, subject: str, html: str) -> None:
    """Synchronous wrapper for the outbox worker (which is not async)."""
    import asyncio

    asyncio.run(send_email(to, subject, html))
