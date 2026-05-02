from typing import Literal

from pydantic import BaseModel


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


class PriceRecommendation(BaseModel):
    online_sell: float | None
    in_mail_buy: float | None
    in_store_buy: float | None
    electronic_buy: float | Literal["No"] | None
    no_data: bool
    confidence: Literal["high", "medium", "low", "none"]
