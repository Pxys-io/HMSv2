"""Patient tags / segments (Plan/14 C4)."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

patient_tag = Table(
    "patient_tag",
    Base.metadata,
    Column("patient_profile_id", ForeignKey("patient_profile.id", ondelete="CASCADE"),
           primary_key=True),
    Column("tag_id", ForeignKey("patient_tag_def.id", ondelete="CASCADE"), primary_key=True),
)


class PatientTag(TimestampMixin, Base):
    __tablename__ = "patient_tag_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    name_ar: Mapped[str | None] = mapped_column(String(60), nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    patients = relationship(
        "PatientProfile", secondary=patient_tag, back_populates="tags"
    )
