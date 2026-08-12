"""ICD-10 catalog (Plan/14 D1)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Icd10Code(Base):
    __tablename__ = "icd10_code"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    label_en: Mapped[str] = mapped_column(String(300))
    label_ar: Mapped[str | None] = mapped_column(String(300), nullable=True)
