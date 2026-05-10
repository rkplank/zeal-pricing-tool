from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

from zeal.db.connection import get_connection
from zeal.db.repositories import (
    MERCHANT_CONFIG_FIELDS,
    MerchantConfigRow,
    MerchantConfigValue,
    RecommendationSnapshot,
    fetch_merchant_config,
    fetch_merchant_detail,
    update_merchant_config,
)
from zeal.web.templating import templates

router = APIRouter()
TIERS = ("T24", "C", "Z", "NC")
PERCENT_FIELDS = ("in_store_margin", "in_mail_margin", "e_bonus", "ebay_differential")
OVERRIDE_FIELDS = ("online_sell_override", "electronic_buy_override")
CHECKBOX_FIELDS = (
    "in_store_eligible",
    "in_mail_eligible",
    "electronic_eligible",
    "merch_credit_variant",
    "is_active",
)
CHART_CHANNELS = (
    ("online_sell", "Online sell", "#145ea8"),
    ("in_mail_buy", "In-mail buy", "#256047"),
    ("ebay_sell_pct", "eBay sell", "#8a5b00"),
    ("in_store_buy", "In-store buy", "#6d4fb3"),
    ("electronic_buy", "Electronic buy", "#b14f22"),
)
CHART_WIDTH = 720
CHART_HEIGHT = 260
CHART_LEFT = 54
CHART_RIGHT = 18
CHART_TOP = 16
CHART_BOTTOM = 42


@dataclass(frozen=True)
class ConfigFormParseResult:
    values: dict[str, MerchantConfigValue]
    reason: str | None
    errors: dict[str, str]


@dataclass(frozen=True)
class ChartSegment:
    points: str


@dataclass(frozen=True)
class PriceHistorySeries:
    label: str
    color: str
    segments: list[ChartSegment]


@dataclass(frozen=True)
class ChartTick:
    label: str
    y: float


@dataclass(frozen=True)
class PriceHistoryChart:
    has_chart: bool
    series: list[PriceHistorySeries]
    y_ticks: list[ChartTick]
    first_label: str
    last_label: str
    empty_message: str | None = None


@router.get("/merchant/{merchant_id}")
def merchant_detail(request: Request, merchant_id: str) -> object:
    conn = get_connection(request.app.state.db_path)
    try:
        bundle = fetch_merchant_detail(conn, merchant_id)
    finally:
        conn.close()
    if bundle is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return templates.TemplateResponse(
        request,
        "merchant_detail.html",
        {
            "merchant": bundle,
            "price_history_chart": build_price_history_chart(bundle.history),
            "title": bundle.display_name,
            "saved": request.query_params.get("saved") == "1",
            **_mode_context(request),
        },
    )


@router.get("/merchant/{merchant_id}/config")
def merchant_config_form(request: Request, merchant_id: str) -> object:
    conn = get_connection(request.app.state.db_path)
    try:
        config = fetch_merchant_config(conn, merchant_id)
    finally:
        conn.close()
    if config is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return _render_config_form(
        request,
        config,
        form_values=_form_values_from_config(config),
        errors={},
        status_code=200,
    )


@router.post("/merchant/{merchant_id}/config")
async def save_merchant_config(request: Request, merchant_id: str) -> object:
    conn = get_connection(request.app.state.db_path)
    try:
        config = fetch_merchant_config(conn, merchant_id)
        if config is None:
            raise HTTPException(status_code=404, detail="Merchant not found")
        form_values = _parse_urlencoded_form(await request.body())
        parsed = _parse_config_form(form_values)
        if parsed.errors:
            return _render_config_form(
                request,
                config,
                form_values=form_values,
                errors=parsed.errors,
                status_code=400,
            )
        update_merchant_config(conn, merchant_id, parsed.values, reason=parsed.reason)
    finally:
        conn.close()
    return RedirectResponse(f"/merchant/{merchant_id}?saved=1", status_code=303)


def _mode_context(request: Request) -> dict[str, object]:
    config = request.app.state.zeal_config
    is_synthetic = config.ebay_mode == "synthetic"
    return {
        "ebay_mode_label": "Synthetic" if is_synthetic else "Live eBay",
        "is_synthetic_mode": is_synthetic,
    }


def build_price_history_chart(history_desc: list[RecommendationSnapshot]) -> PriceHistoryChart:
    if len(history_desc) < 2:
        return PriceHistoryChart(
            has_chart=False,
            series=[],
            y_ticks=[],
            first_label="",
            last_label="",
            empty_message="History chart will appear after two recommendations exist.",
        )
    history = list(reversed(history_desc))
    values = [
        numeric_value
        for snapshot in history
        for field, _, _ in CHART_CHANNELS
        if (numeric_value := _chart_value(getattr(snapshot, field))) is not None
    ]
    if not values:
        return PriceHistoryChart(
            has_chart=False,
            series=[],
            y_ticks=[],
            first_label="",
            last_label="",
            empty_message="No plottable recommendation values are available yet.",
        )
    min_value, max_value = _chart_domain(values)
    y_ticks = [
        ChartTick(label=_format_pct_tick(value), y=_chart_y(value, min_value, max_value))
        for value in (max_value, (min_value + max_value) / 2, min_value)
    ]
    series = [
        series
        for field, label, color in CHART_CHANNELS
        if (
            series := _build_chart_series(
                history,
                field=field,
                label=label,
                color=color,
                min_value=min_value,
                max_value=max_value,
            )
        )
        is not None
    ]
    if not series:
        return PriceHistoryChart(
            has_chart=False,
            series=[],
            y_ticks=[],
            first_label="",
            last_label="",
            empty_message="History chart will appear after two usable points exist.",
        )
    return PriceHistoryChart(
        has_chart=True,
        series=series,
        y_ticks=y_ticks,
        first_label=_date_label(history[0].computed_at),
        last_label=_date_label(history[-1].computed_at),
    )


def _chart_domain(values: list[float]) -> tuple[float, float]:
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        padding = 0.02
    else:
        padding = max((max_value - min_value) * 0.12, 0.01)
    return max(0.0, min_value - padding), min(1.0, max_value + padding)


def _build_chart_series(
    history: list[RecommendationSnapshot],
    *,
    field: str,
    label: str,
    color: str,
    min_value: float,
    max_value: float,
) -> PriceHistorySeries | None:
    segments: list[ChartSegment] = []
    current: list[str] = []
    last_index = len(history) - 1
    for index, snapshot in enumerate(history):
        value = _chart_value(getattr(snapshot, field))
        if value is None:
            if len(current) >= 2:
                segments.append(ChartSegment(points=" ".join(current)))
            current = []
            continue
        current.append(
            f"{_chart_x(index, last_index):.1f},{_chart_y(value, min_value, max_value):.1f}"
        )
    if len(current) >= 2:
        segments.append(ChartSegment(points=" ".join(current)))
    if not segments:
        return None
    return PriceHistorySeries(label=label, color=color, segments=segments)


def _chart_value(value: object) -> float | None:
    if not isinstance(value, int | float):
        return None
    numeric_value = float(value)
    if not isfinite(numeric_value):
        return None
    return numeric_value


def _chart_x(index: int, last_index: int) -> float:
    plot_width = CHART_WIDTH - CHART_LEFT - CHART_RIGHT
    return CHART_LEFT + (index / last_index) * plot_width


def _chart_y(value: float, min_value: float, max_value: float) -> float:
    plot_height = CHART_HEIGHT - CHART_TOP - CHART_BOTTOM
    if max_value == min_value:
        return CHART_TOP + plot_height / 2
    return CHART_TOP + ((max_value - value) / (max_value - min_value)) * plot_height


def _format_pct_tick(value: float) -> str:
    return f"{value * 100:.1f}%"


def _date_label(value: str) -> str:
    if not value:
        return "Unknown date"
    return str(value).split("T", maxsplit=1)[0].split(" ", maxsplit=1)[0] or "Unknown date"


def _render_config_form(
    request: Request,
    config: MerchantConfigRow,
    *,
    form_values: dict[str, str],
    errors: dict[str, str],
    status_code: int,
) -> object:
    return templates.TemplateResponse(
        request,
        "merchant_config.html",
        {
            "config": config,
            "form_values": form_values,
            "errors": errors,
            "tiers": TIERS,
            "title": f"Edit {config.display_name}",
            **_mode_context(request),
        },
        status_code=status_code,
    )


def _form_values_from_config(config: MerchantConfigRow) -> dict[str, str]:
    return {
        "display_name": config.display_name,
        "tier": config.tier,
        "in_store_margin": _format_percent_input(config.in_store_margin),
        "in_mail_margin": _format_percent_input(config.in_mail_margin),
        "e_bonus": _format_percent_input(config.e_bonus),
        "ebay_differential": _format_percent_input(config.ebay_differential),
        "in_store_eligible": _checkbox_value(config.in_store_eligible),
        "in_mail_eligible": _checkbox_value(config.in_mail_eligible),
        "electronic_eligible": _checkbox_value(config.electronic_eligible),
        "online_sell_override": _format_percent_input(config.online_sell_override),
        "electronic_buy_override": _format_percent_input(config.electronic_buy_override),
        "merch_credit_variant": _checkbox_value(config.merch_credit_variant),
        "inclusion_regex": config.inclusion_regex,
        "exclusion_regex": config.exclusion_regex or "",
        "notes": config.notes or "",
        "is_active": _checkbox_value(config.is_active),
        "reason": "",
    }


def _parse_config_form(form: dict[str, str]) -> ConfigFormParseResult:
    errors: dict[str, str] = {}
    values: dict[str, MerchantConfigValue] = {}
    values["display_name"] = _required_text(form, "display_name", errors)
    values["tier"] = _parse_tier(form, errors)
    values["is_active"] = _parse_checkbox(form, "is_active")
    values["in_mail_eligible"] = _parse_checkbox(form, "in_mail_eligible")
    values["in_store_eligible"] = _parse_checkbox(form, "in_store_eligible")
    values["electronic_eligible"] = _parse_checkbox(form, "electronic_eligible")
    values["in_store_margin"] = _parse_percent(form, "in_store_margin", errors, nullable=False)
    values["in_mail_margin"] = _parse_percent(form, "in_mail_margin", errors, nullable=False)
    values["e_bonus"] = _parse_percent(form, "e_bonus", errors, nullable=True)
    values["ebay_differential"] = _parse_percent(
        form,
        "ebay_differential",
        errors,
        nullable=False,
    )
    values["online_sell_override"] = _parse_percent(
        form,
        "online_sell_override",
        errors,
        nullable=True,
    )
    values["electronic_buy_override"] = _parse_percent(
        form,
        "electronic_buy_override",
        errors,
        nullable=True,
    )
    values["merch_credit_variant"] = _parse_checkbox(form, "merch_credit_variant")
    values["inclusion_regex"] = _required_text(form, "inclusion_regex", errors)
    values["exclusion_regex"] = _optional_text(form, "exclusion_regex")
    values["notes"] = _optional_text(form, "notes")
    reason = _optional_text(form, "reason")
    ordered_values = {field: values[field] for field in MERCHANT_CONFIG_FIELDS}
    return ConfigFormParseResult(values=ordered_values, reason=reason, errors=errors)


def _parse_urlencoded_form(body: bytes) -> dict[str, str]:
    return {
        key: value
        for key, value in parse_qsl(
            body.decode("utf-8"),
            keep_blank_values=True,
            encoding="utf-8",
        )
    }


def _required_text(form: dict[str, str], field: str, errors: dict[str, str]) -> str:
    value = form.get(field, "").strip()
    if not value:
        errors[field] = "Required."
    return value


def _optional_text(form: dict[str, str], field: str) -> str | None:
    value = form.get(field, "").strip()
    return value or None


def _parse_tier(form: dict[str, str], errors: dict[str, str]) -> str:
    tier = form.get("tier", "").strip()
    if tier not in TIERS:
        errors["tier"] = "Choose a valid tier."
    return tier


def _parse_checkbox(form: dict[str, str], field: str) -> int:
    return 1 if form.get(field) == "1" else 0


def _parse_percent(
    form: dict[str, str],
    field: str,
    errors: dict[str, str],
    *,
    nullable: bool,
) -> float | None:
    raw = form.get(field, "").strip()
    if not raw:
        if nullable:
            return None
        errors[field] = "Required."
        return None
    cleaned = raw.removesuffix("%").strip()
    try:
        percent = Decimal(cleaned)
    except InvalidOperation:
        errors[field] = "Enter a percentage like 85 or 85%."
        return None
    if 0 < percent <= 1:
        errors[field] = "Enter human percentages like 85 or 85%, not fractions like 0.85."
        return None
    if percent < 0 or percent > 100:
        errors[field] = "Enter a percentage from 0 to 100."
        return None
    return float(percent / Decimal(100))


def _format_percent_input(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value * 100:.1f}"


def _checkbox_value(value: bool) -> str:
    return "1" if value else ""
