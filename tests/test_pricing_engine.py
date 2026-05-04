import pytest

from zeal.models.merchant import MerchantConfig
from zeal.models.pricing import CompetitorAggregate, GlobalConstants
from zeal.pricing.engine import compute_prices

_ABS = 0.001

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

_CASES = [
    (
        "standard_all_channels",
        0.85,
        "high",
        MerchantConfig(
            merchant_id="test",
            display_name="Test",
            tier="C",
            merch_credit_variant=False,
            ebay_differential=0.045,
            in_store_margin=0.25,
            in_mail_margin=0.07,
            e_bonus=0.08,
            in_store_eligible=True,
            in_mail_eligible=True,
            electronic_eligible=True,
        ),
        {
            "online_sell": 0.805,
            "in_mail_buy": 0.655,
            "in_store_buy": 0.447,
            "electronic_buy": 0.575,
            "no_data": False,
        },
    ),
    (
        "electronic_override_with_in_mail_ineligible",
        0.875,
        "high",
        MerchantConfig(
            merchant_id="test",
            display_name="Test",
            tier="Z",
            merch_credit_variant=True,
            ebay_differential=0.025,
            in_store_margin=0.30,
            in_mail_margin=0.15,
            e_bonus=0.13,
            in_store_eligible=False,
            in_mail_eligible=False,
            electronic_eligible=True,
            electronic_buy_override=0.65,
        ),
        {
            "online_sell": 0.850,
            "in_mail_buy": "No",
            "in_store_buy": "No",
            "electronic_buy": 0.65,
            "no_data": False,
        },
    ),
    (
        "pattern_a_online_sell_override_no_ebay_data",
        None,
        "none",
        MerchantConfig(
            merchant_id="test",
            display_name="Test",
            tier="NC",
            merch_credit_variant=False,
            ebay_differential=0.025,
            in_store_margin=0.30,
            in_mail_margin=0.15,
            e_bonus=0.17,
            in_store_eligible=True,
            in_mail_eligible=True,
            electronic_eligible=True,
            online_sell_override=0.85,
        ),
        {
            "online_sell": 0.85,
            "in_mail_buy": 0.62,
            "in_store_buy": 0.442,
            "electronic_buy": 0.45,
            "no_data": False,
        },
    ),
    (
        "no_data_propagation",
        None,
        "none",
        MerchantConfig(
            merchant_id="test",
            display_name="Test",
            tier="C",
            merch_credit_variant=False,
            ebay_differential=0.045,
            in_store_margin=0.25,
            in_mail_margin=0.07,
            e_bonus=0.08,
            in_store_eligible=True,
            in_mail_eligible=True,
            electronic_eligible=True,
        ),
        {
            "online_sell": "No Data",
            "in_mail_buy": "No Data",
            "in_store_buy": "No Data",
            "electronic_buy": "No Data",
            "no_data": True,
        },
    ),
]


@pytest.mark.parametrize("case_id, ebay_sell_pct, confidence, config, expected", _CASES)
def test_compute_prices(case_id, ebay_sell_pct, confidence, config, expected) -> None:
    result = compute_prices(
        ebay_sell_pct,
        confidence,
        CompetitorAggregate(),
        config,
        _CONSTANTS,
    )

    assert_channel(result.online_sell.final_value, expected["online_sell"])
    assert_channel(result.in_mail_buy.final_value, expected["in_mail_buy"])
    assert_channel(result.in_store_buy.final_value, expected["in_store_buy"])
    assert_channel(result.electronic_buy.final_value, expected["electronic_buy"])
    assert result.no_data is expected["no_data"], case_id


def assert_channel(actual: object, expected: object) -> None:
    if isinstance(expected, str):
        assert actual == expected
    else:
        assert actual == pytest.approx(expected, abs=_ABS)
