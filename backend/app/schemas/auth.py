from typing import Annotated

import email_validator
from pydantic import AfterValidator, BaseModel, Field

from app.core.config import get_settings


def _valid_email(value: str) -> str:
    email_validator.validate_email(
        value, test_environment=get_settings().APP_ENV in ("dev", "test")
    )
    return value


Email = Annotated[str, AfterValidator(_valid_email)]


class StaffLoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)


class PatientLoginRequest(BaseModel):
    email_or_phone: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class PatientRegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: Email | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserCreate(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    full_name_ar: str | None = None
    phone: str | None = None
    role: str = "secretary"  # admin | doctor | secretary


class UserUpdate(BaseModel):
    full_name: str | None = None
    full_name_ar: str | None = None
    phone: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class DoctorCreate(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    full_name_ar: str | None = None
    phone: str | None = None
    specialty: str = Field(min_length=2, max_length=120)
    title: str | None = None
    bio: str | None = None
    bio_ar: str | None = None
    booking_mode: str = "slots"  # slots | day_queue
    default_slot_minutes: int = 20
    buffer_minutes: int = 0
    day_capacity: int | None = None
    slot_capacity: int = 1
    billing_mode: str = "per_visit"  # per_visit | per_hour
    hourly_rate: float | None = None
    is_bookable_online: bool = True


class DoctorUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    full_name_ar: str | None = None
    email: Email | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    specialty: str | None = Field(default=None, min_length=2, max_length=120)
    title: str | None = None
    bio: str | None = None
    bio_ar: str | None = None
    booking_mode: str | None = None
    default_slot_minutes: int | None = None
    buffer_minutes: int | None = None
    day_capacity: int | None = None
    slot_capacity: int | None = None
    billing_mode: str | None = None
    hourly_rate: float | None = None
    is_bookable_online: bool | None = None
    public_asset_id: int | None = None
