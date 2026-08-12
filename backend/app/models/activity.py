"""Per-patient activity stream (Plan/14 C2)."""

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ActivityEvent(TimestampMixin, Base):
    __tablename__ = "activity_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_profile_id: Mapped[int] = mapped_column(
        ForeignKey("patient_profile.id", ondelete="CASCADE"), index=True
    )
    actor_type: Mapped[str] = mapped_column(String(16), default="staff")  # staff | public
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    type: Mapped[str] = mapped_column(String(60), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
