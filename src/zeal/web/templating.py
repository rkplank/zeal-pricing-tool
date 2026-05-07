from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def configure_template_filters() -> None:
    templates.env.filters["pct"] = _format_pct
    templates.env.filters["pp"] = _format_pp
    templates.env.filters["channel"] = _format_channel
    templates.env.filters["confidence"] = _format_confidence
    templates.env.filters["datetime"] = _format_datetime
    templates.env.filters["step_label"] = _format_step_label
    templates.env.tests["status_step"] = _is_status_step


def _format_pct(value: object, missing: str = "No recommendation") -> str:
    if value is None:
        return missing
    if isinstance(value, int | float):
        return f"{float(value) * 100:.1f}%"
    return str(value)


def _format_pp(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, int | float):
        sign = "+" if float(value) > 0 else ""
        return f"{sign}{float(value) * 100:.1f}pp"
    return str(value)


def _format_confidence(value: object) -> str:
    labels = {
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "none": "No eBay data",
    }
    return labels.get(str(value), str(value))


def _format_datetime(value: object) -> str:
    if value is None:
        return "never"
    raw = str(value).strip()
    if raw == "":
        return "never"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return raw
    hour = dt.strftime("%I").lstrip("0") or "0"
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}, {hour}:{dt.strftime('%M %p')}"


def _format_channel(value: object) -> str:
    labels = {
        "online_sell": "Online sell",
        "in_mail_buy": "In-mail buy",
        "in_store_buy": "In-store buy",
        "electronic_buy": "Electronic buy",
        "buy_mail": "In-mail buy",
        "buy_electronic": "Electronic buy",
        "sell": "Sell",
        "marketplace_sell": "Marketplace sell",
    }
    return labels.get(str(value), str(value))


def _format_step_label(value: object) -> str:
    labels = {
        "ebay_sell_pct": "eBay sell %",
        "online_sell_ebay": "Online sell, eBay path",
        "in_mail_buy_ebay": "In-mail buy, eBay path",
        "in_store_buy_ebay": "In-store buy, eBay path",
        "electronic_buy_ebay": "Electronic buy, eBay path",
        "e_bonus": "Electronic markdown",
        "paypal_sell_costs": "PayPal cost",
        "online_store_postage_costs": "Online store postage",
        "in_mail_bad_debt": "In-mail bad debt",
        "in_store_bad_debt": "In-store bad debt",
        "in_mail_margin": "In-mail margin",
        "in_store_margin": "In-store margin",
        "ebay_differential": "eBay differential",
        "online_sell_override": "Manual online sell override",
        "electronic_buy_override": "Manual electronic buy override",
        "no_ebay_data_and_override_unset": "No eBay data and no override set",
        "ebay_only_due_to_missing_competitor_data": (
            "Using eBay-only recommendation; no competitor data is available"
        ),
        "no_competitor_analogue": "No competitor analogue for in-store buy",
        "channel_ineligible": "Channel is not eligible",
        "electronic_eligible": "Electronic channel eligibility",
    }
    raw = str(value)
    return labels.get(raw, raw.replace("_", " ").capitalize())


def _is_status_step(value: object) -> bool:
    status_labels = {
        "no_ebay_data_and_override_unset",
        "ebay_only_due_to_missing_competitor_data",
        "no_competitor_analogue",
        "channel_ineligible",
    }
    return str(value) in status_labels
