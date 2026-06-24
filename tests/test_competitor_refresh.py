"""Tests for the competitor refresh orchestrator.

All tests use in-memory SQLite and a mock client — no real CardCashClient, no live network.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from zeal.db.connection import apply_schema
from zeal.ingestion.competitor.errors import CompetitorClientError
from zeal.ingestion.competitor.refresh import run_competitor_refresh
from zeal.models.competitor import CompetitorObservation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
_TS = "2026-06-22T12:00:00"


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    # Seed the cardcash competitor_sources row (normally done by zeal seed).
    conn.execute(
        """
        INSERT INTO competitor_sources
            (source_name, is_active, collection_method, refresh_interval_days)
        VALUES ('cardcash', 1, 'scraper', 7)
        """
    )
    conn.commit()
    return conn


def _add_merchant(
    conn: sqlite3.Connection,
    merchant_id: str,
    display_name: str,
    cardcash_id: int,
    *,
    is_active: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO merchants (
            merchant_id, display_name, tier,
            in_store_margin, in_mail_margin, ebay_differential,
            in_store_eligible, in_mail_eligible, electronic_eligible,
            merch_credit_variant, inclusion_regex, is_active, cardcash_id
        ) VALUES (?, ?, 'T24', 0.05, 0.05, 0.02, 1, 1, 1, 0, '.*', ?, ?)
        """,
        (merchant_id, display_name, is_active, cardcash_id),
    )
    conn.commit()


def _sell_obs(merchant_id: str) -> CompetitorObservation:
    return CompetitorObservation(
        merchant_id=merchant_id,
        source_name="cardcash",
        channel="sell",
        price_pct=0.984,
        availability="available",
        confidence="medium",
        observed_at=_TS,
    )


def _buy_obs(merchant_id: str) -> CompetitorObservation:
    return CompetitorObservation(
        merchant_id=merchant_id,
        source_name="cardcash",
        channel="buy_electronic",
        price_pct=0.83,
        availability="available",
        confidence="high",
        observed_at=_TS,
    )


def _mock_client(
    observations: dict[str, list[CompetitorObservation]],
    source_name: str = "cardcash",
) -> Any:
    """Build a mock CompetitorClient whose fetch_observations returns per-merchant obs."""

    async def _fetch(
        *, merchant_id: str, source_key: int, observed_at: datetime
    ) -> list[CompetitorObservation]:
        return observations.get(merchant_id, [])

    client = AsyncMock()
    client.source_name = source_name
    client.fetch_observations = AsyncMock(side_effect=_fetch)
    return client


# ---------------------------------------------------------------------------
# Full-loop success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_loop_success_two_merchants() -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot", 27)
    _add_merchant(conn, "starbucks", "Starbucks", 54)

    obs_map = {
        "home_depot": [_sell_obs("home_depot"), _buy_obs("home_depot")],
        "starbucks": [_sell_obs("starbucks"), _buy_obs("starbucks")],
    }
    client = _mock_client(obs_map)

    summary = await run_competitor_refresh(db=conn, client=client, now=_NOW)

    assert summary.status == "completed"
    assert summary.processed == 2
    assert summary.total == 2
    assert summary.errored_merchants == []

    run_row = conn.execute(
        "SELECT * FROM refresh_runs WHERE id = ?", (summary.refresh_run_id,)
    ).fetchone()
    assert run_row["kind"] == "competitor"
    assert run_row["status"] == "completed"
    assert run_row["processed"] == 2
    assert run_row["total"] == 2

    obs_count = conn.execute("SELECT COUNT(*) FROM competitor_observations").fetchone()[0]
    assert obs_count == 4


# ---------------------------------------------------------------------------
# refresh_runs kind discriminator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_run_kind_is_competitor() -> None:
    conn = _make_db()
    _add_merchant(conn, "target", "Target", 100)
    client = _mock_client({"target": [_sell_obs("target")]})

    summary = await run_competitor_refresh(db=conn, client=client, now=_NOW)

    row = conn.execute(
        "SELECT kind FROM refresh_runs WHERE id = ?", (summary.refresh_run_id,)
    ).fetchone()
    assert row["kind"] == "competitor"


# ---------------------------------------------------------------------------
# Partial failure: one merchant errors, others succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_failure_continues_after_merchant_error() -> None:
    conn = _make_db()
    _add_merchant(conn, "amazon", "Amazon", 10)
    _add_merchant(conn, "target", "Target", 100)
    _add_merchant(conn, "walmart", "Walmart", 200)

    call_count = 0

    async def _flaky_fetch(
        *, merchant_id: str, source_key: int, observed_at: datetime
    ) -> list[CompetitorObservation]:
        nonlocal call_count
        call_count += 1
        if merchant_id == "target":
            raise ValueError("transient per-merchant failure")
        return [_sell_obs(merchant_id)]

    client = AsyncMock()
    client.source_name = "cardcash"
    client.fetch_observations = AsyncMock(side_effect=_flaky_fetch)

    summary = await run_competitor_refresh(db=conn, client=client, now=_NOW)

    assert summary.status == "partial"
    assert summary.processed == 3  # all counted, including the errored one
    assert summary.total == 3
    assert summary.errored_merchants == ["target"]

    obs_count = conn.execute("SELECT COUNT(*) FROM competitor_observations").fetchone()[0]
    assert obs_count == 2  # amazon and walmart succeeded


# ---------------------------------------------------------------------------
# Catastrophic abort: CompetitorClientError aborts the run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catastrophic_abort_on_competitor_client_error() -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot", 27)
    _add_merchant(conn, "starbucks", "Starbucks", 54)

    async def _catastrophic(
        *, merchant_id: str, source_key: int, observed_at: datetime
    ) -> list[CompetitorObservation]:
        raise CompetitorClientError("Session bootstrap failed: HTTP 503")

    client = AsyncMock()
    client.source_name = "cardcash"
    client.fetch_observations = AsyncMock(side_effect=_catastrophic)

    summary = await run_competitor_refresh(db=conn, client=client, now=_NOW)

    assert summary.status == "failed"
    assert summary.processed == 0

    run_row = conn.execute(
        "SELECT status, error FROM refresh_runs WHERE id = ?", (summary.refresh_run_id,)
    ).fetchone()
    assert run_row["status"] == "failed"
    assert "Session bootstrap failed" in run_row["error"]

    obs_count = conn.execute("SELECT COUNT(*) FROM competitor_observations").fetchone()[0]
    assert obs_count == 0


# ---------------------------------------------------------------------------
# --limit slices merchants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limit_slices_merchant_list() -> None:
    conn = _make_db()
    # Ordered by display_name: Amazon, Target, Walmart
    _add_merchant(conn, "amazon", "Amazon", 10)
    _add_merchant(conn, "target", "Target", 100)
    _add_merchant(conn, "walmart", "Walmart", 200)

    called_ids: list[str] = []

    async def _record(
        *, merchant_id: str, source_key: int, observed_at: datetime
    ) -> list[CompetitorObservation]:
        called_ids.append(merchant_id)
        return [_sell_obs(merchant_id)]

    client = AsyncMock()
    client.source_name = "cardcash"
    client.fetch_observations = AsyncMock(side_effect=_record)

    summary = await run_competitor_refresh(db=conn, client=client, now=_NOW, limit=2)

    assert summary.total == 2
    assert summary.processed == 2
    assert called_ids == ["amazon", "target"]  # first 2 by display_name order


# ---------------------------------------------------------------------------
# competitor_sources timestamps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_last_successful_refresh_updated_on_success() -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot", 27)
    client = _mock_client({"home_depot": [_sell_obs("home_depot")]})

    await run_competitor_refresh(db=conn, client=client, now=_NOW)

    row = conn.execute(
        "SELECT last_attempted_refresh, last_successful_refresh"
        " FROM competitor_sources WHERE source_name = 'cardcash'"
    ).fetchone()
    assert row["last_attempted_refresh"] == _TS
    assert row["last_successful_refresh"] == _TS


@pytest.mark.asyncio
async def test_last_successful_refresh_not_updated_on_catastrophic_failure() -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot", 27)

    async def _fail(**_: object) -> list[CompetitorObservation]:
        raise CompetitorClientError("cart create failed")

    client = AsyncMock()
    client.source_name = "cardcash"
    client.fetch_observations = AsyncMock(side_effect=_fail)

    await run_competitor_refresh(db=conn, client=client, now=_NOW)

    row = conn.execute(
        "SELECT last_attempted_refresh, last_successful_refresh"
        " FROM competitor_sources WHERE source_name = 'cardcash'"
    ).fetchone()
    assert row["last_attempted_refresh"] == _TS
    assert row["last_successful_refresh"] is None


# ---------------------------------------------------------------------------
# Append-only: re-running inserts new rows, not update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observations_are_append_only() -> None:
    conn = _make_db()
    _add_merchant(conn, "target", "Target", 100)
    client = _mock_client({"target": [_sell_obs("target")]})

    await run_competitor_refresh(db=conn, client=client, now=_NOW)
    await run_competitor_refresh(db=conn, client=client, now=_NOW)

    obs_count = conn.execute("SELECT COUNT(*) FROM competitor_observations").fetchone()[0]
    assert obs_count == 2  # two runs → two rows for same merchant
