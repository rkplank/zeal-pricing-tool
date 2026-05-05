from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from zeal.db.connection import DEFAULT_DB_PATH
from zeal.web.routes import dashboard, merchant
from zeal.web.templating import WEB_DIR, configure_template_filters


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="Zeal Pricing Tool")
    app.state.db_path = db_path
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    configure_template_filters()

    app.include_router(dashboard.router)
    app.include_router(merchant.router)
    return app


app = create_app()
