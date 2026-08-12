"""Structured lab results + trends (Plan/14 D2)."""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class LabResult(TimestampMixin, Base):
    __tablename__ = "lab_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit.id", ondelete="CASCADE"),
        index=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"),
        index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[float] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_min: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    ref_max: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    result_date: Mapped[date] = mapped_column(Date, index=True)
