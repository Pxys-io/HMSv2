"""Scheduling + patient schemas (Plan/03)."""

from datetime import date, time

from pydantic import BaseModel, Field


class VisitTypeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    name_ar: str = Field(min_length=2, max_length=120)
    category: str = Field(default="other", pattern="^(new_visit|follow_up|procedure|other)$")
    duration_minutes: int = Field(default=20, ge=5, le=480)
    default_price: float = Field(ge=0)
    color: str | None = Field(default=None, max_length=7)
    is_active: bool = True


class VisitTypeUpdate(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    category: str | None = Field(default=None, pattern="^(new_visit|follow_up|procedure|other)$")
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    default_price: float | None = Field(default=None, ge=0)
    color: str | None = None
    is_active: bool | None = None


class ScheduleCreate(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0=Mon .. 6=Sun
    start_time: time
    end_time: time
    effective_from: date | None = None
    effective_to: date | None = None


class ScheduleUpdate(BaseModel):
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool | None = None


class BlockCreate(BaseModel):
    date_from: date
    date_to: date
    reason: str | None = Field(default=None, max_length=200)


class AppointmentCreate(BaseModel):
    patient_profile_id: int
    doctor_id: int
    visit_type_id: int
    date: date
    start_time: time | None = None
    follow_up_of_id: int | None = None
    force: bool = False


class AppointmentMove(BaseModel):
    date: date
    start_time: time | None = None


class AppointmentCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class PublicAppointmentCreate(BaseModel):
    profile_id: int
    doctor_id: int
    visit_type_id: int
    date: date
    start_time: time | None = None


class PatientProfileCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    custom_data: dict | None = None
    full_name_ar: str | None = None
    gender: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None
    phone: str = Field(min_length=6, max_length=32)
    phone_alt: str | None = None
    address: str | None = Field(default=None, max_length=300)
    allergies: str | None = None
    chronic_conditions: str | None = None


class PatientProfileUpdate(BaseModel):
    full_name: str | None = None
    custom_data: dict | None = None
    full_name_ar: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    phone_alt: str | None = None
    address: str | None = None
