from typing import Literal

from pydantic import BaseModel

type Confidence = Literal["high", "medium", "low", "none"]
type ValidityStatus = Literal["valid", "excluded", "suspicious"]


class EbaySoldListing(BaseModel):
    listing_id: str
    sold_at: str
    face_value: float
    sale_price: float
    title: str
    source_url: str | None = None
    raw_payload: str | None = None


class EbayObservation(BaseModel):
    merchant_id: str
    listing_id: str
    sold_at: str
    face_value: float
    sale_price: float
    title: str
    validity_status: ValidityStatus = "valid"
    exclusion_reason: str | None = None
    id: int | None = None
    raw_payload: str | None = None
    fetched_at: str = ""


