from __future__ import annotations

from fastapi import APIRouter, Request

from zeal.db.connection import get_connection
from zeal.db.repositories import fetch_pricing_list, fetch_pricing_list_summary
from zeal.web.templating import mode_context, templates

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
            **mode_context(request),
        },
    )
