from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from zeal.db.connection import get_connection
from zeal.db.repositories import fetch_merchant_detail
from zeal.web.templating import templates

router = APIRouter()


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
            "title": bundle.display_name,
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
