import pytest

from zeal.models.merchant import MerchantConfig
from zeal.models.pricing import CompetitorAggregate, GlobalConstants
from zeal.pricing.blending import blend_values
from zeal.pricing.engine import compute_prices

_CONSTANTS = GlobalConstants(
    ebay_sale_costs=0.13,
    paypal_sell_costs=0.03,
    ebay_postage_costs=0.01,
    online_store_postage_costs=0.03,
    online_sell_bonus_competitive=0.065,
    online_sell_bonus_zen_nocomp=0.085,
    in_store_bad_debt=0.048,
    in_mail_bad_debt=0.02,
    online_bad_debt=0.05,
)


def _config(*, ebay_weight: float = 1.0) -> MerchantConfig:
    return MerchantConfig(
        merchant_id="home_depot",
        display_name="Home Depot",
        tier="C",
        in_store_margin=0.25,
        in_mail_margin=0.07,
        e_bonus=0.08,
        ebay_differential=0.045,
        in_store_eligible=True,
        in_mail_eligible=True,
        electronic_eligible=True,
        merch_credit_variant=False,
        ebay_weight=ebay_weight,
    )


def test_blend_values_uses_ebay_only_at_weight_one() -> None:
    assert blend_values(0.725, 0.74, 1.0) == pytest.approx(0.725)


def test_ebay_weight_blends_applicable_channels() -> None:
    result = compute_prices(
        0.92,
        "high",
        CompetitorAggregate(online_sell=0.90, in_mail_buy=0.74, electronic_buy=0.68),
        _config(ebay_weight=0.7),
        _CONSTANTS,
    )

    assert result.online_sell.final_value == pytest.approx(0.8825)
    assert result.in_mail_buy.final_value == pytest.approx(0.7295)
    assert result.electronic_buy.final_value == pytest.approx(0.6555)


def test_missing_competitor_falls_back_to_ebay() -> None:
    result = compute_prices(
        0.92,
        "high",
        CompetitorAggregate(),
        _config(ebay_weight=0.0),
        _CONSTANTS,
    )
    assert result.online_sell.final_value == pytest.approx(0.875)
    assert result.in_mail_buy.final_value == pytest.approx(0.725)
    assert result.electronic_buy.final_value == pytest.approx(0.645)


def test_in_store_is_unaffected_by_competitor() -> None:
    result = compute_prices(
        0.92,
        "high",
        CompetitorAggregate(online_sell=0.50, in_mail_buy=0.50, electronic_buy=0.50),
        _config(ebay_weight=0.0),
        _CONSTANTS,
    )
    assert result.in_store_buy.final_value == pytest.approx(0.517)


def test_no_ebay_data_is_not_replaced_by_competitor_only_value() -> None:
    result = compute_prices(
        None,
        "none",
        CompetitorAggregate(online_sell=0.90, in_mail_buy=0.74, electronic_buy=0.68),
        _config(ebay_weight=0.0),
        _CONSTANTS,
    )
    assert result.online_sell.final_value == "No Data"
    assert result.in_mail_buy.final_value == "No Data"
    assert result.electronic_buy.final_value == "No Data"
