from typing import Literal

from pydantic import BaseModel

type Confidence = Literal["high", "medium", "low", "none"]


class EbayObservation(BaseModel):
    merchant_id: str
    listing_id: str
    sold_at: str
    face_value: float
    sale_price: float
    title: str
    id: int | None = None
    raw_payload: str | None = None
    fetched_at: str = ""


class EbaySummary(BaseModel):
    merchant_id: str
    summary_date: str
    sample_size: int
    confidence: Confidence
    ebay_sell_pct: float | None = None
    most_recent_observation: str | None = None
