"""Tests for POST /refresh and GET /refresh/status routes."""
from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

from fastapi.testclient import TestClient

from zeal.db.connection import apply_schema, get_connection
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data
from zeal.ingestion.ebay_client import EbaySoldListing
from zeal.web.app import create_app

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _bare_db(tmp_path: Path) -> Path:
    """Schema-only DB — no merchants, no constants, no runs."""
    db_path = tmp_path / "zeal.db"
    conn = get_connection(db_path)
    apply_schema(conn)
    conn.close()
    return db_path


def _seeded_db(tmp_path: Path) -> Path:
    """Full demo DB with merchants, constants, and a completed baseline run."""
    db_path = tmp_path / "zeal.db"
    conn = get_connection(db_path)
    apply_schema(conn)
    seed_demo_data(conn, BASELINE_FIXTURE)
    conn.close()
    return db_path


def _seed_running_row(db_path: Path, total: int = 10) -> int:
    """Insert a refresh_runs row with status='running' and return its id."""
    conn = get_connection(db_path)
    try:
        run_id = conn.execute(
            "INSERT INTO refresh_runs (status, total, processed) "
            "VALUES ('running', ?, 0) RETURNING id",
            (total,),
        ).fetchone()[0]
        conn.commit()
        return int(run_id)
    finally:
        conn.close()


def _latest_row(db_path: Path) -> sqlite3.Row | None:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT * FROM refresh_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Slow eBay client (suspends forever — keeps the background task pending)
# ---------------------------------------------------------------------------


class _SlowClient:
    async def sold_listings_for_merchant(
        self,
        *,
        merchant_id: str,
        inclusion_regex: str,
        exclusion_regex: str | None,
    ) -> Sequence[EbaySoldListing]:
        await asyncio.sleep(9999)
        return []


# ---------------------------------------------------------------------------
# GET /refresh/status
# ---------------------------------------------------------------------------


def test_status_no_runs_returns_idle_never(tmp_path: Path) -> None:
    app = create_app(_bare_db(tmp_path))
    client = TestClient(app)

    response = client.get("/refresh/status")

    assert response.status_code == 200
    assert "Refresh now" in response.text
    assert "never" in response.text


def test_status_while_running_returns_running_partial(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    app = create_app(db_path)
    app.state.ebay_client_factory = lambda: _SlowClient()
    client = TestClient(app)

    client.post("/refresh")
    response = client.get("/refresh/status")

    assert response.status_code == 200
    assert 'hx-get="/refresh/status"' in response.text
    assert "every 2s" in response.text
    assert "Refresh now" not in response.text


def test_status_after_run_finishes_returns_idle_with_hx_trigger(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    app = create_app(db_path)
    # Default SyntheticEbayClient — fast, completes quickly
    client = TestClient(app)

    post_resp = client.post("/refresh")
    assert post_resp.status_code == 200

    # Poll until the background task finishes and the idle partial is returned.
    resp = None
    for _ in range(50):
        time.sleep(0.1)
        resp = client.get("/refresh/status")
        if "Refresh now" in resp.text:
            break

    assert resp is not None
    assert resp.status_code == 200
    assert "Refresh now" in resp.text
    assert resp.headers.get("HX-Trigger") == "refreshList"


def test_status_failed_run_returns_idle_with_timestamp(tmp_path: Path) -> None:
    db_path = _bare_db(tmp_path)
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO refresh_runs (status, completed_at, total, processed) "
        "VALUES ('failed', '2025-06-01T12:00:00', 5, 2)"
    )
    conn.commit()
    conn.close()

    app = create_app(db_path)
    client = TestClient(app)

    response = client.get("/refresh/status")

    assert response.status_code == 200
    assert "Refresh now" in response.text
    assert "2025-06-01T12:00:00" in response.text


def test_status_partial_run_returns_idle_with_timestamp(tmp_path: Path) -> None:
    db_path = _bare_db(tmp_path)
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO refresh_runs (status, completed_at, total, processed) "
        "VALUES ('partial', '2025-06-02T08:30:00', 10, 9)"
    )
    conn.commit()
    conn.close()

    app = create_app(db_path)
    client = TestClient(app)

    response = client.get("/refresh/status")

    assert response.status_code == 200
    assert "Refresh now" in response.text
    assert "2025-06-02T08:30:00" in response.text


# ---------------------------------------------------------------------------
# POST /refresh
# ---------------------------------------------------------------------------


def test_post_refresh_starts_run_returns_running_partial(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    app = create_app(db_path)
    app.state.ebay_client_factory = lambda: _SlowClient()
    client = TestClient(app)

    response = client.post("/refresh")

    assert response.status_code == 200
    assert 'hx-get="/refresh/status"' in response.text
    assert "every 2s" in response.text

    row = _latest_row(db_path)
    assert row is not None
    assert row["status"] == "running"


def test_post_refresh_while_in_flight_returns_409(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    app = create_app(db_path)
    app.state.ebay_client_factory = lambda: _SlowClient()
    client = TestClient(app)

    first = client.post("/refresh")
    assert first.status_code == 200

    second = client.post("/refresh")
    assert second.status_code == 409


def test_post_refresh_with_stale_db_running_row_returns_409(tmp_path: Path) -> None:
    db_path = _bare_db(tmp_path)
    _seed_running_row(db_path)

    # Create app WITHOUT entering the lifespan context so the startup hook
    # does not clean up the stale row — simulating the "impossible" path.
    app = create_app(db_path)
    client = TestClient(app)  # intentionally not a context manager

    response = client.post("/refresh")

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------


def test_startup_hook_marks_interrupted_runs_failed(tmp_path: Path) -> None:
    db_path = _bare_db(tmp_path)
    run_id = _seed_running_row(db_path, total=5)

    app = create_app(db_path)
    with TestClient(app):
        # lifespan has fired by the time we are inside the with block
        pass

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM refresh_runs WHERE id = ?", (run_id,)
    ).fetchone()
    conn.close()

    assert row["status"] == "failed"
    assert row["error"] == "interrupted by server restart"
