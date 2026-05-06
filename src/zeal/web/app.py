from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from zeal.config import ZealConfig
from zeal.db.connection import DEFAULT_DB_PATH, get_connection
from zeal.ingestion.ebay_client import SyntheticEbayClient
from zeal.ingestion.ebay_client_factory import create_ebay_client
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
    config = ZealConfig.from_env()
    app.state.http_client = httpx.AsyncClient()
    ebay_client = create_ebay_client(config=config, http_client=app.state.http_client)
    if app.state.ebay_client_factory is app.state.default_ebay_client_factory:
        app.state.ebay_client_factory = lambda: ebay_client
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="Zeal Pricing Tool", lifespan=_lifespan)
    app.state.db_path = db_path
    app.state.refresh_task = None
    app.state.refresh_lock = asyncio.Lock()
    app.state.default_ebay_client_factory = lambda: SyntheticEbayClient()
    app.state.ebay_client_factory = app.state.default_ebay_client_factory
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    configure_template_filters()

    app.include_router(dashboard.router)
    app.include_router(merchant.router)
    app.include_router(refresh.router)
    return app


app = create_app()
