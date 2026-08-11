"""Financial schemas (Plan/06)."""

from pydantic import BaseModel, Field


class PricingRow(BaseModel):
    visit_type_id: int
    doctor_id: int | None = None
    price: float = Field(ge=0)


class PricingPut(BaseModel):
    rows: list[PricingRow] = Field(max_length=500)


class SyndicateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    name_ar: str | None = None
    code: str = Field(min_length=2, max_length=40)
    contact_phone: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class SyndicateUpdate(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class SyndicatePriceItem(BaseModel):
    visit_type_id: int
    doctor_id: int | None = None
    syndicate_coverage: float = Field(ge=0)
    patient_share: float = Field(ge=0, default=0)


class SyndicatePricePut(BaseModel):
    items: list[SyndicatePriceItem] = Field(max_length=500)


class InvoiceItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    description_ar: str | None = None
    qty: float = Field(default=1, gt=0)
    unit_price: float = Field(ge=0)


class ManualInvoiceCreate(BaseModel):
    patient_profile_id: int
    doctor_id: int
    syndicate_id: int | None = None
    items: list[InvoiceItemIn] = Field(min_length=1, max_length=50)


class DiscountIn(BaseModel):
    kind: str = Field(pattern="^(percent|fixed)$")
    value: float = Field(ge=0)
    reason: str | None = Field(default=None, max_length=300)


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: str = Field(pattern="^(cash|card|fawry|instapay|wallet|meeza)$")
    reference: str | None = Field(default=None, max_length=120)


class RefundIn(BaseModel):
    amount: float | None = Field(default=None, gt=0)
