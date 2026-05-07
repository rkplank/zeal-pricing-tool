from __future__ import annotations

from fastapi import APIRouter, Request

from zeal.db.connection import get_connection
from zeal.db.repositories import fetch_pricing_list, fetch_pricing_list_summary
from zeal.web.templating import templates

router = APIRouter()


@router.get("/")
def pricing_list(request: Request) -> object:
    conn = get_connection(request.app.state.db_path)
    try:
        rows = fetch_pricing_list(conn, delta_window=5)
        summary = fetch_pricing_list_summary(conn, rows)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "rows": rows,
            "summary": summary,
            "title": "Pricing List",
            **_mode_context(request),
        },
    )


def _mode_context(request: Request) -> dict[str, object]:
    config = request.app.state.zeal_config
    is_synthetic = config.ebay_mode == "synthetic"
    return {
        "ebay_mode_label": "Synthetic" if is_synthetic else "Live eBay",
        "is_synthetic_mode": is_synthetic,
    }
