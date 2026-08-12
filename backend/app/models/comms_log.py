"""Per-patient communication log (Plan/14 C3)."""

from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class CommunicationLogEntry(TimestampMixin, Base):
    __tablename__ = "communication_log_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profile.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(
        Enum("call", "email", "whatsapp", "sms", "in_person", name="comm_channel"),
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"), nullable=True)
