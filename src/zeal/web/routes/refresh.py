from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from zeal.db.connection import get_connection
from zeal.ingestion.refresh import run_refresh
from zeal.models.pricing import GlobalConstants
from zeal.web.templating import mode_context, templates

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _load_constants(conn: sqlite3.Connection) -> GlobalConstants:
    rows = conn.execute("SELECT key, value FROM global_constants").fetchall()
    return GlobalConstants(**{row["key"]: row["value"] for row in rows})


def _latest_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        conn.execute(
            "SELECT * FROM refresh_runs ORDER BY id DESC LIMIT 1"
        ).fetchone(),
    )


def _last_terminal_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return cast(
        sqlite3.Row | None,
        conn.execute(
            """SELECT * FROM refresh_runs
               WHERE status IN ('completed', 'partial', 'failed')
               ORDER BY id DESC LIMIT 1"""
        ).fetchone(),
    )


def _running_ctx(row: sqlite3.Row | None) -> dict[str, object]:
    if row is None:
        return {"processed": 0, "total": 0, "started_at": None}
    return {
        "processed": row["processed"],
        "total": row["total"],
        "started_at": row["started_at"],
    }


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_in_background(db_path: Path, ebay_client_factory: object) -> None:
    conn = get_connection(db_path)
    try:
        constants = _load_constants(conn)
        # Factory returns SyntheticEbayClient or EbayMarketplaceInsightsClient
        # based on ZEAL_EBAY_MODE. No code change needed; flip .env to go live.
        ebay_client = ebay_client_factory()  # type: ignore[operator]

        async def _commit_progress(processed: int, total: int) -> None:
            conn.commit()

        await run_refresh(
            db=conn,
            ebay_client=ebay_client,
            constants=constants,
            progress_hook=_commit_progress,
        )
    except Exception:
        logger.exception("Uncaught exception in background refresh task")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def start_refresh(request: Request) -> object:
    if request.app.state.zeal_config.ebay_mode == "synthetic":
        return HTMLResponse(
            status_code=409,
            content="Refresh is disabled in synthetic mode",
        )

    async with request.app.state.refresh_lock:
        task: asyncio.Task[object] | None = request.app.state.refresh_task
        if task is not None and not task.done():
            return HTMLResponse(status_code=409, content="Refresh already in progress")

        conn = get_connection(request.app.state.db_path)
        try:
            row = _latest_run(conn)
        finally:
            conn.close()

        if row is not None and row["status"] == "running":
            return HTMLResponse(status_code=409, content="Refresh already in progress")

        request.app.state.refresh_task = asyncio.create_task(
            _run_in_background(
                request.app.state.db_path,
                request.app.state.ebay_client_factory,
            )
        )

    # Yield so the task can start and insert the refresh_runs row before we read it.
    await asyncio.sleep(0)

    conn = get_connection(request.app.state.db_path)
    try:
        row = _latest_run(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "partials/refresh_running.html",
        _running_ctx(row),
    )


@router.get("/refresh/status")
async def refresh_status(request: Request) -> object:
    task: asyncio.Task[object] | None = request.app.state.refresh_task
    had_task = task is not None

    conn = get_connection(request.app.state.db_path)
    try:
        row = _latest_run(conn)
        last = _last_terminal_run(conn)
    finally:
        conn.close()

    if row is not None and row["status"] == "running":
        return templates.TemplateResponse(
            request,
            "partials/refresh_running.html",
            _running_ctx(row),
        )

    response = templates.TemplateResponse(
        request,
        "partials/refresh_idle.html",
        {
            "last_completed": last["completed_at"] if last else None,
            **mode_context(request),
        },
    )
    # Signal list re-fetch only when transitioning from a task started in this
    # server session (had_task) to a terminal state, so page-load requests for
    # an already-idle region don't fire an unnecessary refreshList event.
    if had_task and (task is None or task.done()):
        response.headers["HX-Trigger"] = "refreshList"
        request.app.state.refresh_task = None
    return response
