"""Billing models: pricing, syndicates, invoices, payments."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class PriceListItem(TimestampMixin, Base):
    __tablename__ = "price_list_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_type_id: Mapped[int] = mapped_column(ForeignKey("visit_type.id"))
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctor.id"),
        nullable=True)  # null = clinic default
    price: Mapped[float] = mapped_column(Numeric(12, 2))

    __table_args__ = (Index("uq_price_visit_doctor", "visit_type_id", "doctor_id", unique=True),)


class Syndicate(TimestampMixin, Base):
    __tablename__ = "syndicate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SyndicatePrice(TimestampMixin, Base):
    __tablename__ = "syndicate_price"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    syndicate_id: Mapped[int] = mapped_column(ForeignKey("syndicate.id"))
    visit_type_id: Mapped[int] = mapped_column(ForeignKey("visit_type.id"))
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctor.id"), nullable=True)
    syndicate_coverage: Mapped[float] = mapped_column(
        Numeric(12, 2)  # amount billed to the syndicate
    )
    patient_share: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    __table_args__ = (
        Index("uq_syndicate_price", "syndicate_id", "visit_type_id", "doctor_id", unique=True),
    )


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    patient_profile_id: Mapped[int] = mapped_column(ForeignKey("patient_profile.id"), index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("visit.id"), unique=True, nullable=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointment.id"), nullable=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctor.id"))
    syndicate_id: Mapped[int | None] = mapped_column(ForeignKey("syndicate.id"), nullable=True)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2))
    discount_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2))
    patient_due: Mapped[float] = mapped_column(Numeric(12, 2))
    syndicate_due: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    paid_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    refunded_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EGP")
    status: Mapped[str] = mapped_column(
        Enum("issued", "partially_paid", "paid", "refunded", "cancelled",
            name="invoice_status"), default="issued"
    )
    issued_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    record_version: Mapped[int] = mapped_column(Integer, default=1)
    reissue_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoice.id"), nullable=True
    )


class InvoiceItem(TimestampMixin, Base):
    __tablename__ = "invoice_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id", ondelete="CASCADE"),
        index=True)
    description: Mapped[str] = mapped_column(String(300))
    description_ar: Mapped[str | None] = mapped_column(String(300), nullable=True)
    qty: Mapped[float] = mapped_column(Numeric(8, 2), default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2))
    line_total: Mapped[float] = mapped_column(Numeric(12, 2))
    visit_type_id: Mapped[int | None] = mapped_column(ForeignKey("visit_type.id"), nullable=True)


class Discount(TimestampMixin, Base):
    __tablename__ = "discount"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id", ondelete="CASCADE"),
        index=True)
    kind: Mapped[str] = mapped_column(Enum("percent", "fixed", name="discount_kind"))
    value: Mapped[float] = mapped_column(Numeric(8, 2))
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    granted_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))


class Payment(TimestampMixin, Base):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id", ondelete="CASCADE"),
        index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(
        Enum("cash", "card", "fawry", "instapay", "wallet", "meeza", name="payment_method")
    )
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    received_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False)
