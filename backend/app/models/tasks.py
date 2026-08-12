"""Internal tasks (Plan/14 C5)."""

from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Task(TimestampMixin, Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"),
        nullable=True, index=True)
    priority: Mapped[str] = mapped_column(
        Enum("low", "medium", "high", name="task_priority"), default="medium"
    )
    status: Mapped[str] = mapped_column(
        Enum("open", "in_progress", "done", name="task_status"), default="open", index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
