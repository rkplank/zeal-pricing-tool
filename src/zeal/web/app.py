from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from zeal.db.connection import DEFAULT_DB_PATH, get_connection
from zeal.ingestion.ebay_client import SyntheticEbayClient
from zeal.web.routes import dashboard, merchant, refresh
from zeal.web.templating import WEB_DIR, configure_template_filters


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Mark any refresh that was in flight when the server stopped as failed.
    conn = get_connection(app.state.db_path)
    try:
        conn.execute(
            """UPDATE refresh_runs
               SET status = 'failed', error = 'interrupted by server restart'
               WHERE status = 'running'"""
        )
        conn.commit()
    finally:
        conn.close()
    yield


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="Zeal Pricing Tool", lifespan=_lifespan)
    app.state.db_path = db_path
    app.state.refresh_task = None
    app.state.refresh_lock = asyncio.Lock()
    app.state.ebay_client_factory = lambda: SyntheticEbayClient()
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    configure_template_filters()

    app.include_router(dashboard.router)
    app.include_router(merchant.router)
    app.include_router(refresh.router)
    return app


app = create_app()
