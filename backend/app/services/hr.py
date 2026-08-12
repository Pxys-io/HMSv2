"""HR service helpers (Plan/14 F4: absent-after-10am in-app notification)."""


from sqlalchemy import select

from app.models.config import Setting
from app.models.hr import AttendanceRecord
from app.models.identity import StaffUser
from app.services.settings import clinic_now, clinic_today


def notify_absent_staff(db) -> None:
    """F4: once per day, after 10:00 clinic time, notify admins/secretaries
    of staff who have no attendance record today."""
    now = clinic_now()
    if now.time().hour < 10:
        return
    today = clinic_today()
    marker = db.scalar(select(Setting).where(Setting.key == "hr.absence_notified_date"))
    if marker is not None and marker.value == today.isoformat():
        return
    active = db.scalars(select(StaffUser).where(StaffUser.is_active.is_(True))).all()
    clocked = {
        r.staff_user_id for r in db.scalars(
            select(AttendanceRecord).where(AttendanceRecord.date == today)
        ).all()
    }
    absent = [u for u in active if u.id not in clocked]
    if absent:
        from app.services.notify import fan_out

        names = ", ".join(u.full_name for u in absent[:10])
        fan_out(
            db, type="hr_absent", title="Staff absent today",
            body=f"{len(absent)} staff have not clocked in: {names}",
            link="/finance", roles=("admin", "secretary"),
        )
        db.commit()
    if marker is None:
        db.add(Setting(key="hr.absence_notified_date", value=today.isoformat()))
    else:
        marker.value = today.isoformat()
    db.commit()
