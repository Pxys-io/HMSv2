"""Chat / notifications / reminders tests (Plan/08 §8)."""

import secrets

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.comms import ChatConversation, OutboxEvent
from tests.conftest import csrf_headers


def register_patient(client, email=None):
    email = email or f"ch-{secrets.token_hex(4)}@example.com"
    resp = client.post(
        "/api/public/auth/register",
        json={"full_name": "Chatter", "email": email, "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def staff_token(client):
    client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    )
    token = client.post(
        "/api/auth/login", json={"email": "admin@example.com", "password": "passw0rd"},
        headers=csrf_headers(client),
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_guest_chat_flow(client):
    headers = staff_token(client)
    # guest start -> cookie
    start = client.post(
        "/api/public/chat/start",
        json={"message": "Do you have evening slots?", "guest_name": "Guest",
              "guest_contact": "01000000000"},
        headers=csrf_headers(client),
    )
    assert start.status_code == 200
    assert "hmsv2_guest_key" in client.cookies
    conversation_id = start.json()["conversation_id"]

    # staff sees the conversation
    convos = client.get("/api/chat/conversations", headers=headers).json()
    assert any(c["id"] == conversation_id for c in convos)
    assert convos[0]["guest_name"] == "Guest"
    assert convos[0]["unread_staff"] == 1

    # staff replies -> auto-assign + unread_patient
    reply = client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        json={"body": "Yes, 5-7 PM daily"},
        headers=headers,
    )
    assert reply.status_code == 200
    db = SessionLocal()
    conversation = db.get(ChatConversation, conversation_id)
    assert conversation.assigned_to is not None
    assert conversation.unread_patient == 1
    db.close()

    # guest polls (cookie + csrf not needed for GET)
    poll = client.get("/api/public/chat/messages?since_id=0")
    assert poll.status_code == 200
    bodies = [m["body"] for m in poll.json()["messages"]]
    assert "Yes, 5-7 PM daily" in bodies

    # guest sends
    sent = client.post(
        "/api/public/chat/messages",
        json={"body": "Great, see you tomorrow"},
        headers=csrf_headers(client),
    )
    assert sent.status_code == 200
    convos = client.get("/api/chat/conversations", headers=headers).json()
    match = [c for c in convos if c["id"] == conversation_id]
    assert match and match[0]["unread_staff"] >= 1


def test_account_chat_reuses_conversation(client):
    token = register_patient(client)
    auth = {"Authorization": f"Bearer {token}"}
    first = client.post(
        "/api/public/chat/start", json={"message": "hello"},
        headers={**auth, **csrf_headers(client)},
    )
    second = client.post(
        "/api/public/chat/start", json={"message": "again"},
        headers={**auth, **csrf_headers(client)},
    )
    assert first.status_code == 200
    assert first.json()["conversation_id"] == second.json()["conversation_id"]


def test_guest_key_is_hashed_at_rest(client):
    client.post(
        "/api/public/chat/start",
        json={"message": "test", "guest_name": "G", "guest_contact": "010"},
        headers=csrf_headers(client),
    )
    raw = client.cookies["hmsv2_guest_key"]
    db = SessionLocal()
    conversation = db.scalar(
        select(ChatConversation).where(ChatConversation.guest_key_hash.isnot(None))
    )
    assert conversation.guest_key_hash != raw
    db.close()


def test_booking_notifies_secretaries_and_enqueues_email(client):
    # register + profile + book
    token = register_patient(client)
    profile = client.post(
        "/api/public/profiles",
        json={"full_name": "Booker", "phone": "01011112222"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    # need a bookable doctor: create via admin
    admin = staff_token(client)
    doctor = client.post(
        "/api/doctors",
        json={"email": f"dr-{secrets.token_hex(4)}@example.com", "password": "passw0rd",
              "full_name": "Bookable Doc", "specialty": "General"},
        headers=admin,
    )
    assert doctor.status_code == 200, doctor.text
    doctor_id = doctor.json()["id"]
    from datetime import date, time, timedelta

    from app.db.session import SessionLocal as _SL
    from app.models.identity import Doctor as _Doctor
    from app.models.scheduling import DoctorSchedule, VisitType

    db = _SL()
    doc = db.get(_Doctor, doctor_id)
    doc.booking_mode = "day_queue"
    for wd in range(7):
        db.add(
            DoctorSchedule(
                doctor_id=doctor_id, weekday=wd, start_time=time(17, 0), end_time=time(21, 0)
            )
        )
    vt = VisitType(name="Consultation", name_ar="كشف", duration_minutes=20, default_price=300)
    db.add(vt)
    db.commit()
    vt_id = vt.id
    db.close()

    day = (date.today() + timedelta(days=7)).isoformat()
    booked = client.post(
        "/api/public/appointments",
        json={"profile_id": profile["id"], "doctor_id": doctor_id, "visit_type_id": vt_id,
              "date": day},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "notif-1"},
    )
    assert booked.status_code == 200

    # notification fan-out to secretary + admin
    notifications = client.get("/api/notifications?unread_only=true", headers=admin).json()
    assert any(n["type"] == "booking_new" for n in notifications)

    # confirmation email enqueued in the outbox
    db = SessionLocal()
    outbox = db.scalar(
        select(OutboxEvent).where(OutboxEvent.kind == "email_booking_confirmation")
    )
    assert outbox is not None
    assert outbox.payload["to"]  # patient account email
    db.close()


def test_reminder_link_normalizes_egyptian_phone(client):
    admin = staff_token(client)
    from datetime import date, time

    from app.models.identity import PatientProfile
    from app.models.scheduling import Appointment

    db = SessionLocal()
    profile = PatientProfile(code=f"P-W{secrets.token_hex(4).upper()}",
                             full_name="WhatsApp", phone="01012345678")
    db.add(profile)
    db.flush()
    appointment = Appointment(
        booking_ref=f"BK-W{secrets.token_hex(4).upper()}", patient_profile_id=profile.id,
        doctor_id=1, visit_type_id=1, date=date.today(), start_time=time(17, 0),
        status="booked", source="staff",
    )
    db.add(appointment)
    db.commit()
    appt_id = appointment.id
    db.close()

    link = client.get(f"/api/appointments/{appt_id}/reminder-link?locale=ar", headers=admin)
    assert link.status_code == 200
    body = link.json()
    assert body["url"].startswith("https://wa.me/201012345678?text=")
    assert body["reason"] is None

    # link generation stamped
    db = SessionLocal()
    appt = db.get(Appointment, appt_id)
    assert appt.reminder_link_generated_at is not None
    db.close()

    upcoming = client.get("/api/appointments/reminders/today", headers=admin).json()
    assert any(u["appointment_id"] == appt_id for u in upcoming)
