from __future__ import annotations

from typing import Literal

from zeal.models.merchant import MerchantConfig
from zeal.models.pricing import GlobalConstants, PriceRecommendation


def compute_prices(
    ebay_sell_pct: float | None,
    confidence: Literal["high", "medium", "low", "none"],
    config: MerchantConfig,
    constants: GlobalConstants,
) -> PriceRecommendation:
    # §5.1 Online sell
    if config.online_sell_override is not None:
        online_sell: float | str = config.online_sell_override
    elif ebay_sell_pct is None:
        online_sell = "No Data"
    else:
        online_sell = ebay_sell_pct - config.ebay_differential

    # §5.2 In-mail buy
    if not config.in_mail_eligible:
        in_mail_buy: float | str = "No"
    elif isinstance(online_sell, str):
        in_mail_buy = "No Data"
    else:
        in_mail_buy = (
            online_sell
            - config.in_mail_margin
            - constants.paypal_sell_costs
            - constants.in_mail_bad_debt
            - constants.online_store_postage_costs
        )

    # §5.3 In-store buy
    if not config.in_store_eligible:
        in_store_buy: float | str = "No"
    elif isinstance(online_sell, str):
        in_store_buy = "No Data"
    else:
        in_store_buy = (
            online_sell
            - config.in_store_margin
            - constants.paypal_sell_costs
            - constants.online_store_postage_costs
            - constants.in_store_bad_debt
        )

    # §5.4 Electronic buy — override checked BEFORE in_mail dependency so that
    # merchants with in_mail_eligible=False + electronic_buy_override still get a price.
    if not config.electronic_eligible:
        electronic_buy: float | str = "No"
    elif config.electronic_buy_override is not None:
        electronic_buy = config.electronic_buy_override
    elif isinstance(in_mail_buy, str):  # "No" or "No Data"
        electronic_buy = "No Data"
    else:
        assert config.e_bonus is not None
        electronic_buy = in_mail_buy - config.e_bonus

    no_data = online_sell == "No Data"

    return PriceRecommendation(
        online_sell=None if isinstance(online_sell, str) else online_sell,
        in_mail_buy=None if isinstance(in_mail_buy, str) else in_mail_buy,
        in_store_buy=None if isinstance(in_store_buy, str) else in_store_buy,
        electronic_buy=(
            "No"
            if electronic_buy == "No"
            else None
            if isinstance(electronic_buy, str)
            else electronic_buy
        ),
        no_data=no_data,
        confidence=confidence,
    )
