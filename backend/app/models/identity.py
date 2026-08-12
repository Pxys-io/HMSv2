"""Identity models: staff, doctors, patient accounts/profiles, refresh tokens."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class StaffUser(TimestampMixin, Base):
    __tablename__ = "staff_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    full_name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("role.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    role_obj: Mapped["Role | None"] = relationship("Role", lazy="joined")

    @property
    def role(self) -> str:
        """System-role name for UI/business checks; 'custom' for custom roles."""
        role = self.role_obj
        if role is not None and role.is_system:
            return role.name
        return "custom"

    @property
    def permission_codes(self) -> set[str]:
        return {rp.permission.code for rp in (self.role_obj.permissions if self.role_obj else [])}


class Doctor(TimestampMixin, Base):
    __tablename__ = "doctor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_user_id: Mapped[int] = mapped_column(ForeignKey("staff_user.id"), unique=True)
    specialty: Mapped[str] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_asset_id: Mapped[int | None] = mapped_column(ForeignKey("public_asset.id"),
        nullable=True)
    booking_mode: Mapped[str] = mapped_column(Enum("slots", "day_queue", name="booking_mode"),
        default="slots")
    default_slot_minutes: Mapped[int] = mapped_column(Integer, default=20)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)
    day_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slot_capacity: Mapped[int] = mapped_column(Integer, default=1)
    billing_mode: Mapped[str] = mapped_column(Enum("per_visit", "per_hour", name="billing_mode"),
        default="per_visit")
    hourly_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_bookable_online: Mapped[bool] = mapped_column(Boolean, default=True)


class PatientAccount(TimestampMixin, Base):
    __tablename__ = "patient_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
        nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
        nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    locale: Mapped[str] = mapped_column(Enum("ar", "en", name="locale"), default="ar")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PatientProfile(TimestampMixin, Base):
    __tablename__ = "patient_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("patient_account.id"),
        nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    full_name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gender: Mapped[str | None] = mapped_column(
        Enum("male", "female", "other", "unknown", "prefer_not_to_say",
            name="gender"), nullable=True
    )
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str] = mapped_column(String(32))
    phone_alt: Mapped[str | None] = mapped_column(String(32), nullable=True)
    national_id_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    chronic_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    record_version: Mapped[int] = mapped_column(Integer, default=1)
    syndicate_id: Mapped[int | None] = mapped_column(ForeignKey("syndicate.id"), nullable=True)
    syndicate_member_no: Mapped[str | None] = mapped_column(String(64), nullable=True)


class NumberSequence(TimestampMixin, Base):
    __tablename__ = "number_sequence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(40))
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("scope", "year", name="uq_number_sequence_scope_year"),)


class RefreshToken(TimestampMixin, Base):
    __tablename__ = "refresh_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_type: Mapped[str] = mapped_column(Enum("staff", "patient", name="token_owner_type"))
    owner_id: Mapped[int] = mapped_column(Integer)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Role(TimestampMixin, Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    name_ar: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", lazy="selectin", cascade="all, delete-orphan"
    )


class Permission(TimestampMixin, Base):
    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    label_ar: Mapped[str] = mapped_column(String(120), default="")
    group: Mapped[str] = mapped_column(String(40), default="other")




class RolePermission(TimestampMixin, Base):
    __tablename__ = "role_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission.id", ondelete="CASCADE"))
    permission: Mapped["Permission"] = relationship("Permission", lazy="joined")

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )
