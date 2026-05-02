# Firewall unit tests for compute_prices.
# Expected values are hand-verified; do not recompute from the spec.
#
# Sentinel representation (PriceRecommendation as of session 2):
#   online_sell / in_mail_buy / in_store_buy: float | None
#     None covers both "No" (channel ineligible) and "No Data" (no eBay input).
#     no_data:bool disambiguates the eBay-data case at the top level.
#   electronic_buy: float | Literal["No"] | None
#     "No" = channel ineligible; None = no eBay data propagated.

import pytest
from zeal.pricing.engine import compute_prices

from zeal.models.merchant import MerchantConfig
from zeal.models.pricing import GlobalConstants

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
        "standard_all_channels",  # standard 4-channel formula, no overrides
        (
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
        "electronic_override_with_in_mail_ineligible",  # override bypasses in_mail dependency
        (
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
        ),
        {
            "online_sell": 0.850,
            "in_mail_buy": None,    # "No" — in_mail_eligible=False
            "in_store_buy": None,   # "No" — in_store_eligible=False
            "electronic_buy": 0.65,
            "no_data": False,
        },
    ),
    (
        "pattern_a_online_sell_override_no_ebay_data",  # Pattern A: hardcoded online_sell
        (
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
        "no_data_propagation",  # no eBay data, no override — all channels "No Data"
        (
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
        ),
        {
            "online_sell": None,    # "No Data"
            "in_mail_buy": None,    # "No Data" propagated
            "in_store_buy": None,   # "No Data" propagated
            "electronic_buy": None, # "No Data" propagated
            "no_data": True,
        },
    ),
]


@pytest.mark.parametrize(
    "case_id, inputs, expected",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_compute_prices(case_id, inputs, expected):
    ebay_sell_pct, confidence, config = inputs
    result = compute_prices(ebay_sell_pct, confidence, config, _CONSTANTS)

    if expected["online_sell"] is None:
        assert result.online_sell is None
    else:
        assert result.online_sell == pytest.approx(expected["online_sell"], abs=_ABS)

    if expected["in_mail_buy"] is None:
        assert result.in_mail_buy is None
    else:
        assert result.in_mail_buy == pytest.approx(expected["in_mail_buy"], abs=_ABS)

    if expected["in_store_buy"] is None:
        assert result.in_store_buy is None
    else:
        assert result.in_store_buy == pytest.approx(expected["in_store_buy"], abs=_ABS)

    if expected["electronic_buy"] is None:
        assert result.electronic_buy is None
    else:
        assert result.electronic_buy == pytest.approx(expected["electronic_buy"], abs=_ABS)

    assert result.no_data is expected["no_data"]
