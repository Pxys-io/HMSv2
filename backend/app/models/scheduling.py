"""Scheduling models: visit types, doctor shifts, blocks, appointments."""

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class VisitType(TimestampMixin, Base):
    __tablename__ = "visit_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=20)
    default_price: Mapped[float] = mapped_column(Numeric(12, 2))
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DoctorSchedule(TimestampMixin, Base):
    __tablename__ = "doctor_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"), index=True)
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0=Mon .. 6=Sun
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ScheduleBlock(TimestampMixin, Base):
    __tablename__ = "schedule_block"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"), index=True)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_ref: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"), index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"), index=True)
    visit_type_id: Mapped[int] = mapped_column(ForeignKey("visit_type.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)  # null in day_queue mode
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("booked", "checked_in", "in_progress", "completed", "cancelled", "no_show",
            name="appointment_status"),
        default="booked",
        index=True,
    )
    source: Mapped[str] = mapped_column(
        Enum("public", "staff", "walk_in", name="appointment_source")
    )
    follow_up_of_id: Mapped[int | None] = mapped_column(ForeignKey("appointment.id"), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reminder_link_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
        nullable=True)
    booked_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"),
        nullable=True)

    __table_args__ = (
        Index("ix_appointment_doctor_date_status", "doctor_id", "date", "status"),
    )
