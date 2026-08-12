"""HR models: attendance, leaves, payroll (Plan/14 F)."""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AttendanceRecord(TimestampMixin, Base):
    __tablename__ = "attendance_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    check_in: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("staff_user_id", "date", name="uq_attendance_day"),)


class LeaveRequest(TimestampMixin, Base):
    __tablename__ = "leave_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"), index=True)
    leave_type: Mapped[str] = mapped_column(String(40))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    days: Mapped[float] = mapped_column(Numeric(5, 1))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "approved", "rejected", "cancelled", name="leave_status"),
        default="pending", index=True,
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PayrollRun(TimestampMixin, Base):
    __tablename__ = "payroll_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), unique=True, index=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "paid", name="payroll_status"), default="draft"
    )
    generated_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    items: Mapped[list["PayrollLineItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class PayrollLineItem(TimestampMixin, Base):
    __tablename__ = "payroll_line_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_run.id", ondelete="CASCADE"), index=True
    )
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    base_salary: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    allowances: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    deductions: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    gross: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    social_insurance: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    net: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    run: Mapped[PayrollRun] = relationship(back_populates="items")
