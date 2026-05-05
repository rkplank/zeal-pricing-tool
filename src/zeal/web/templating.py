from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")


def configure_template_filters() -> None:
    templates.env.filters["pct"] = _format_pct
    templates.env.filters["pp"] = _format_pp
    templates.env.filters["channel"] = _format_channel


def _format_pct(value: object) -> str:
    if value is None:
        return "—"
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


def _format_channel(value: object) -> str:
    labels = {
        "online_sell": "Online sell",
        "in_mail_buy": "In-mail buy",
        "in_store_buy": "In-store buy",
        "electronic_buy": "Electronic buy",
    }
    return labels.get(str(value), str(value))
