"""EMR models: visits, diagnoses, medications, prescriptions, attachments."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Visit(TimestampMixin, Base):
    __tablename__ = "visit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"), index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"), index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointment.id"), nullable=True)
    queue_entry_id: Mapped[int | None] = mapped_column(ForeignKey("queue_entry.id"), nullable=True)
    visit_type_id: Mapped[int] = mapped_column(ForeignKey("visit_type.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[str | None] = mapped_column(Text, nullable=True)
    vitals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    clinical_exam: Mapped[str | None] = mapped_column(Text, nullable=True)
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    labs: Mapped[str | None] = mapped_column(Text, nullable=True)
    imaging: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_next_visit: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_private: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follow_up_due: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(Enum("open", "completed", name="visit_status"),
        default="open")
    record_version: Mapped[int] = mapped_column(Integer, default=1)
    last_saved_by: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"), nullable=True)

    __table_args__ = (Index("ix_visit_profile_created", "patient_profile_id", "created_at"),)


class VisitDiagnosis(TimestampMixin, Base):
    __tablename__ = "visit_diagnosis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Enum("differential", "final", name="diagnosis_kind"))
    label: Mapped[str] = mapped_column(String(300))
    icd10_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    order: Mapped[int] = mapped_column(SmallInteger, default=0)


class Medication(TimestampMixin, Base):
    __tablename__ = "medication"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    form: Mapped[str] = mapped_column(String(60))
    strength: Mapped[str] = mapped_column(String(60))
    default_dose: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_frequency: Mapped[str | None] = mapped_column(String(120), nullable=True)
    default_duration: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("uq_medication_name_form_strength", "name", "form", "strength", unique=True),
    )


class Prescription(TimestampMixin, Base):
    __tablename__ = "prescription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visit.id"), unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))


class PrescriptionItem(TimestampMixin, Base):
    __tablename__ = "prescription_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescription.id", ondelete="CASCADE"),
        index=True)
    medication_id: Mapped[int | None] = mapped_column(ForeignKey("medication.id"), nullable=True)
    free_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    dose: Mapped[str] = mapped_column(String(120))
    frequency: Mapped[str] = mapped_column(String(120))
    duration: Mapped[str] = mapped_column(String(60))
    instructions: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quantity: Mapped[str | None] = mapped_column(String(60), nullable=True)
    order: Mapped[int] = mapped_column(SmallInteger, default=0)


class Attachment(TimestampMixin, Base):
    __tablename__ = "attachment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"), index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit.id"), nullable=True)
    kind: Mapped[str] = mapped_column(
        Enum("lab", "imaging", "report", "photo", "other", name="attachment_kind")
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500))
    thumb_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    scan_status: Mapped[str] = mapped_column(
        Enum("pending", "clean", "rejected", name="scan_status"), default="pending"
    )
    uploaded_by_type: Mapped[str] = mapped_column(Enum("staff", name="uploader_type"),
        default="staff")
    uploaded_by_id: Mapped[int] = mapped_column(Integer)
