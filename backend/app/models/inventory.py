"""Inventory/pharmacy models (Plan/14 E)."""

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
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


class ProductCategory(TimestampMixin, Base):
    __tablename__ = "product_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    name_ar: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Product(TimestampMixin, Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_category.id"), nullable=True
    )
    medication_id: Mapped[int | None] = mapped_column(
        ForeignKey("medication.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    form: Mapped[str | None] = mapped_column(String(40), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(60), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(60), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="unit")
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    reorder_level: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("name", "strength", name="uq_product_name_strength"),)


class StockLevel(Base):
    __tablename__ = "stock_level"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0)


class StockMovement(TimestampMixin, Base):
    __tablename__ = "stock_movement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    kind: Mapped[str] = mapped_column(
        Enum("in", "out", "adjust", "opening", name="stock_kind"), index=True
    )
    qty: Mapped[float] = mapped_column(Numeric(12, 2))
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2))
    ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_user.id"), nullable=True)


class Supplier(TimestampMixin, Base):
    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_number: Mapped[str] = mapped_column(String(40), unique=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("draft", "ordered", "partially_received", "received", name="po_status"),
        default="ordered", index=True,
    )
    ordered_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("staff_user.id"))
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="po", cascade="all, delete-orphan"
    )


class PurchaseOrderItem(TimestampMixin, Base):
    __tablename__ = "purchase_order_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id", ondelete="CASCADE"),
        index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[float] = mapped_column(Numeric(12, 2))
    received_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    po: Mapped[PurchaseOrder] = relationship(back_populates="items")
