from __future__ import annotations

from typing import Literal

from zeal.models.merchant import MerchantConfig
from zeal.models.pricing import (
    BreakdownStep,
    ChannelResult,
    ChannelValue,
    CompetitorAggregate,
    GlobalConstants,
    PriceRecommendation,
)
from zeal.pricing.blending import blend_values

type Confidence = Literal["high", "medium", "low", "none"]


def compute_prices(
    ebay_sell_pct: float | None,
    ebay_confidence: Confidence,
    competitor: CompetitorAggregate,
    config: MerchantConfig,
    constants: GlobalConstants,
) -> PriceRecommendation:
    online_sell_ebay = _compute_online_sell_ebay(ebay_sell_pct, config)
    online_sell = _channel_result(
        channel="online_sell",
        ebay_value=online_sell_ebay,
        competitor_value=competitor.online_sell,
        ebay_weight=config.ebay_weight,
        eBay_steps=_online_sell_steps(ebay_sell_pct, config, online_sell_ebay),
    )

    in_mail_ebay = _compute_in_mail_ebay(online_sell_ebay, config, constants)
    in_mail_competitor = competitor.in_mail_buy if config.in_mail_eligible else None
    in_mail_buy = _channel_result(
        channel="in_mail_buy",
        ebay_value=in_mail_ebay,
        competitor_value=in_mail_competitor,
        ebay_weight=config.ebay_weight,
        eBay_steps=_in_mail_steps(online_sell_ebay, config, constants, in_mail_ebay),
    )

    in_store_ebay = _compute_in_store_ebay(online_sell_ebay, config, constants)
    in_store_buy = ChannelResult(
        final_value=in_store_ebay,
        ebay_only_value=in_store_ebay,
        competitor_only_value=None,
        breakdown=tuple(
            [
                *_in_store_steps(online_sell_ebay, config, constants, in_store_ebay),
                BreakdownStep(label="no_competitor_analogue", value="in_store_buy", sign="="),
            ]
        ),
    )

    electronic_ebay = _compute_electronic_ebay(in_mail_ebay, config)
    electronic_competitor = _compute_electronic_competitor(competitor, config, constants)
    electronic_buy = _channel_result(
        channel="electronic_buy",
        ebay_value=electronic_ebay,
        competitor_value=electronic_competitor,
        ebay_weight=config.ebay_weight,
        eBay_steps=_electronic_steps(in_mail_ebay, config, electronic_ebay),
    )

    return PriceRecommendation(
        online_sell=online_sell,
        in_mail_buy=in_mail_buy,
        in_store_buy=in_store_buy,
        electronic_buy=electronic_buy,
        no_data=online_sell.final_value == "No Data",
        confidence=ebay_confidence,
    )


def _compute_online_sell_ebay(
    ebay_sell_pct: float | None,
    config: MerchantConfig,
) -> ChannelValue:
    if config.online_sell_override is not None:
        return config.online_sell_override
    if ebay_sell_pct is None:
        return "No Data"
    return ebay_sell_pct - config.ebay_differential


def _compute_in_mail_ebay(
    online_sell_ebay: ChannelValue,
    config: MerchantConfig,
    constants: GlobalConstants,
) -> ChannelValue:
    if not config.in_mail_eligible:
        return "No"
    if online_sell_ebay == "No Data" or online_sell_ebay == "No":
        return "No Data"
    return (
        online_sell_ebay
        - config.in_mail_margin
        - constants.paypal_sell_costs
        - constants.in_mail_bad_debt
        - constants.online_store_postage_costs
    )


def _compute_in_store_ebay(
    online_sell_ebay: ChannelValue,
    config: MerchantConfig,
    constants: GlobalConstants,
) -> ChannelValue:
    if not config.in_store_eligible:
        return "No"
    if online_sell_ebay == "No Data" or online_sell_ebay == "No":
        return "No Data"
    return (
        online_sell_ebay
        - config.in_store_margin
        - constants.paypal_sell_costs
        - constants.online_store_postage_costs
        - constants.in_store_bad_debt
    )


def _compute_electronic_ebay(
    in_mail_ebay: ChannelValue,
    config: MerchantConfig,
) -> ChannelValue:
    if not config.electronic_eligible:
        return "No"
    if config.electronic_buy_override is not None:
        return config.electronic_buy_override
    if in_mail_ebay == "No" or in_mail_ebay == "No Data":
        return "No Data"
    assert config.e_bonus is not None
    return in_mail_ebay - config.e_bonus


def _compute_electronic_competitor(
    competitor: CompetitorAggregate,
    config: MerchantConfig,
    constants: GlobalConstants,
) -> float | None:
    if not config.electronic_eligible:
        return None
    if config.electronic_buy_override is not None:
        return config.electronic_buy_override
    if competitor.electronic_buy is not None:
        return competitor.electronic_buy
    if competitor.in_mail_buy is not None:
        return competitor.in_mail_buy - constants.competitor_electronic_markdown
    return None


def _channel_result(
    *,
    channel: str,
    ebay_value: ChannelValue,
    competitor_value: float | None,
    ebay_weight: float,
    eBay_steps: list[BreakdownStep],
) -> ChannelResult:
    steps = list(eBay_steps)
    final_value: ChannelValue
    if ebay_value == "No":
        steps.append(BreakdownStep(label="channel_ineligible", value=channel, sign="="))
        final_value = ebay_value
    elif ebay_value == "No Data":
        steps.append(
            BreakdownStep(label="no_ebay_data_and_override_unset", value=channel, sign="=")
        )
        final_value = ebay_value
    elif competitor_value is None:
        steps.append(
            BreakdownStep(label="ebay_only_due_to_missing_competitor_data", value=channel, sign="=")
        )
        final_value = ebay_value
    else:
        blended = blend_values(ebay_value, competitor_value, ebay_weight)
        steps.extend(
            [
                BreakdownStep(label="ebay_weight", value=ebay_weight, sign="*"),
                BreakdownStep(label="competitor_only", value=competitor_value, sign="blend"),
                BreakdownStep(label="final", value=blended, sign="="),
            ]
        )
        final_value = blended

    return ChannelResult(
        final_value=final_value,
        ebay_only_value=ebay_value,
        competitor_only_value=competitor_value,
        breakdown=tuple(steps),
    )


def _online_sell_steps(
    ebay_sell_pct: float | None,
    config: MerchantConfig,
    result: ChannelValue,
) -> list[BreakdownStep]:
    if config.online_sell_override is not None:
        return [
            BreakdownStep(label="online_sell_override", value=config.online_sell_override, sign="=")
        ]
    if ebay_sell_pct is None:
        return [BreakdownStep(label="ebay_sell_pct", value="No Data", sign="=")]
    return [
        BreakdownStep(label="ebay_sell_pct", value=ebay_sell_pct, sign="="),
        BreakdownStep(label="ebay_differential", value=config.ebay_differential, sign="-"),
        BreakdownStep(label="online_sell_ebay", value=result, sign="="),
    ]


def _in_mail_steps(
    online_sell_ebay: ChannelValue,
    config: MerchantConfig,
    constants: GlobalConstants,
    result: ChannelValue,
) -> list[BreakdownStep]:
    if not config.in_mail_eligible or isinstance(online_sell_ebay, str):
        return [BreakdownStep(label="online_sell_ebay", value=online_sell_ebay, sign="=")]
    return [
        BreakdownStep(label="online_sell_ebay", value=online_sell_ebay, sign="="),
        BreakdownStep(label="in_mail_margin", value=config.in_mail_margin, sign="-"),
        BreakdownStep(label="paypal_sell_costs", value=constants.paypal_sell_costs, sign="-"),
        BreakdownStep(label="in_mail_bad_debt", value=constants.in_mail_bad_debt, sign="-"),
        BreakdownStep(
            label="online_store_postage_costs",
            value=constants.online_store_postage_costs,
            sign="-",
        ),
        BreakdownStep(label="in_mail_buy_ebay", value=result, sign="="),
    ]


def _in_store_steps(
    online_sell_ebay: ChannelValue,
    config: MerchantConfig,
    constants: GlobalConstants,
    result: ChannelValue,
) -> list[BreakdownStep]:
    if not config.in_store_eligible or isinstance(online_sell_ebay, str):
        return [BreakdownStep(label="online_sell_ebay", value=online_sell_ebay, sign="=")]
    return [
        BreakdownStep(label="online_sell_ebay", value=online_sell_ebay, sign="="),
        BreakdownStep(label="in_store_margin", value=config.in_store_margin, sign="-"),
        BreakdownStep(label="paypal_sell_costs", value=constants.paypal_sell_costs, sign="-"),
        BreakdownStep(
            label="online_store_postage_costs",
            value=constants.online_store_postage_costs,
            sign="-",
        ),
        BreakdownStep(label="in_store_bad_debt", value=constants.in_store_bad_debt, sign="-"),
        BreakdownStep(label="in_store_buy_ebay", value=result, sign="="),
    ]


def _electronic_steps(
    in_mail_ebay: ChannelValue,
    config: MerchantConfig,
    result: ChannelValue,
) -> list[BreakdownStep]:
    if not config.electronic_eligible:
        return [BreakdownStep(label="electronic_eligible", value="No", sign="=")]
    if config.electronic_buy_override is not None:
        return [
            BreakdownStep(
                label="electronic_buy_override",
                value=config.electronic_buy_override,
                sign="=",
            )
        ]
    if isinstance(in_mail_ebay, str):
        return [BreakdownStep(label="in_mail_buy_ebay", value=in_mail_ebay, sign="=")]
    assert config.e_bonus is not None
    return [
        BreakdownStep(label="in_mail_buy_ebay", value=in_mail_ebay, sign="="),
        BreakdownStep(label="e_bonus", value=config.e_bonus, sign="-"),
        BreakdownStep(label="electronic_buy_ebay", value=result, sign="="),
    ]
