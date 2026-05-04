from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field


class GlobalConstants(BaseModel):
    ebay_sale_costs: float
    paypal_sell_costs: float
    ebay_postage_costs: float
    online_store_postage_costs: float
    online_sell_bonus_competitive: float
    online_sell_bonus_zen_nocomp: float
    in_store_bad_debt: float
    in_mail_bad_debt: float
    online_bad_debt: float
    competitor_electronic_markdown: float = 0.05


class CompetitorAggregate(BaseModel):
    online_sell: float | None = None
    in_mail_buy: float | None = None
    electronic_buy: float | None = None
    sources_contributing: Sequence[str] = ()


class BreakdownStep(BaseModel):
    label: str
    value: float | str
    sign: Literal["+", "-", "=", "*", "blend"]


type ChannelValue = float | Literal["No", "No Data"]


class ChannelResult(BaseModel):
    final_value: ChannelValue
    ebay_only_value: ChannelValue
    competitor_only_value: float | None = None
    breakdown: Sequence[BreakdownStep] = Field(default_factory=tuple)


class PriceRecommendation(BaseModel):
    online_sell: ChannelResult
    in_mail_buy: ChannelResult
    in_store_buy: ChannelResult
    electronic_buy: ChannelResult
    no_data: bool
    confidence: Literal["high", "medium", "low", "none"]
