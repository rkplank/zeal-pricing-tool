from __future__ import annotations

from fastapi import APIRouter, Request

from zeal.db.connection import get_connection
from zeal.db.repositories import fetch_pricing_list
from zeal.web.templating import templates

router = APIRouter()


@router.get("/")
def pricing_list(request: Request) -> object:
    conn = get_connection(request.app.state.db_path)
    try:
        rows = fetch_pricing_list(conn, delta_window=5)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"rows": rows, "title": "Pricing List"},
    )
