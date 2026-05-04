from typing import Literal

from pydantic import BaseModel

type CollectionMethod = Literal["scraper", "manual", "csv_import"]
type CompetitorChannel = Literal["buy_mail", "buy_electronic", "sell", "marketplace_sell"]
type Availability = Literal["available", "unavailable", "no_data"]
type CompetitorConfidence = Literal["high", "medium", "low", "none"]


class CompetitorSource(BaseModel):
    source_name: str
    is_active: bool = True
    collection_method: CollectionMethod
    refresh_interval_days: int
    last_successful_refresh: str | None = None
    last_attempted_refresh: str | None = None
    notes: str | None = None


class CompetitorObservation(BaseModel):
    merchant_id: str
    source_name: str
    channel: CompetitorChannel
    price_pct: float | None = None
    availability: Availability
    confidence: CompetitorConfidence
    observed_at: str
    source_url: str | None = None
    raw_payload: str | None = None
    notes: str | None = None
