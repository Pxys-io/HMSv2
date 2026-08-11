"""Queue model: same-day arrival queue per (doctor, date)."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class QueueEntry(TimestampMixin, Base):
    __tablename__ = "queue_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    date: Mapped[date] = mapped_column(Date, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointment.id"), nullable=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"))
    visit_type_id: Mapped[int | None] = mapped_column(ForeignKey("visit_type.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("waiting", "called", "in_room", "completed", "left", name="queue_status"),
        default="waiting",
    )
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_queue_doctor_date_seq", "doctor_id", "date", "seq"),)
