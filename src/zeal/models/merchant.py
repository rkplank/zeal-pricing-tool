from typing import Literal

from pydantic import BaseModel, Field


class MerchantConfig(BaseModel):
    merchant_id: str
    display_name: str
    tier: Literal["T24", "C", "Z", "NC"]
    in_store_margin: float
    in_mail_margin: float
    ebay_differential: float
    in_store_eligible: bool
    in_mail_eligible: bool
    electronic_eligible: bool
    merch_credit_variant: bool
    e_bonus: float | None = None
    online_sell_override: float | None = None
    electronic_buy_override: float | None = None
    ebay_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str | None = None


class MerchantRecord(MerchantConfig):
    inclusion_regex: str
    created_at: str
    updated_at: str
    exclusion_regex: str | None = None
    is_active: bool = True
