"""Phase 1 competitor scraper tests — schema, Protocol interface, and seed."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from zeal.db.connection import apply_schema
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data
from zeal.ingestion.competitor.base import CompetitorClient
from zeal.ingestion.competitor.errors import (
    CompetitorClientError,
    CompetitorNetworkError,
    CompetitorRateLimitError,
    CompetitorServerError,
)
from zeal.models.competitor import CompetitorObservation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# Schema: merchants.cardcash_id
# ---------------------------------------------------------------------------


def test_merchants_has_cardcash_id_column() -> None:
    conn = _make_conn()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(merchants)")}
    assert "cardcash_id" in columns


def test_cardcash_id_is_nullable() -> None:
    """Merchants without a CardCash mapping have cardcash_id = NULL."""
    conn = _make_conn()
    conn.execute(
        """
        INSERT INTO merchants (
            merchant_id, display_name, tier,
            in_store_margin, in_mail_margin, ebay_differential,
            in_store_eligible, in_mail_eligible, electronic_eligible,
            merch_credit_variant, inclusion_regex
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("m1", "Test", "T24", 0.25, 0.03, 0.045, 1, 1, 0, 0, "test"),
    )
    row = conn.execute(
        "SELECT cardcash_id FROM merchants WHERE merchant_id = 'm1'"
    ).fetchone()
    assert row is not None
    assert row[0] is None


def test_cardcash_id_stores_integer() -> None:
    conn = _make_conn()
    conn.execute(
        """
        INSERT INTO merchants (
            merchant_id, display_name, tier,
            in_store_margin, in_mail_margin, ebay_differential,
            in_store_eligible, in_mail_eligible, electronic_eligible,
            merch_credit_variant, inclusion_regex, cardcash_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("m2", "Home Depot", "T24", 0.25, 0.045, 0.045, 1, 1, 1, 0, "home.*depot", 27),
    )
    row = conn.execute(
        "SELECT cardcash_id FROM merchants WHERE merchant_id = 'm2'"
    ).fetchone()
    assert row[0] == 27


# ---------------------------------------------------------------------------
# Schema: refresh_runs.kind
# ---------------------------------------------------------------------------


def test_refresh_runs_has_kind_column() -> None:
    conn = _make_conn()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(refresh_runs)")}
    assert "kind" in columns


def test_refresh_runs_kind_defaults_to_ebay() -> None:
    conn = _make_conn()
    conn.execute("INSERT INTO refresh_runs (status, total) VALUES ('running', 10)")
    row = conn.execute("SELECT kind FROM refresh_runs LIMIT 1").fetchone()
    assert row[0] == "ebay"


def test_refresh_runs_kind_accepts_competitor() -> None:
    conn = _make_conn()
    conn.execute(
        "INSERT INTO refresh_runs (kind, status, total) VALUES ('competitor', 'running', 5)"
    )
    row = conn.execute(
        "SELECT kind FROM refresh_runs WHERE kind = 'competitor'"
    ).fetchone()
    assert row[0] == "competitor"


def test_refresh_runs_kind_rejects_invalid_value() -> None:
    conn = _make_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO refresh_runs (kind, status, total) VALUES ('invalid', 'running', 1)"
        )


# ---------------------------------------------------------------------------
# CompetitorClient Protocol
# ---------------------------------------------------------------------------


class _StubClient:
    """Minimal implementation of the CompetitorClient Protocol for testing."""

    @property
    def source_name(self) -> str:
        return "cardcash"

    async def fetch_observations(
        self,
        *,
        merchant_id: str,
        source_key: int,
        observed_at: datetime,
    ) -> list[CompetitorObservation]:
        return []


def test_stub_client_source_name() -> None:
    client = _StubClient()
    assert client.source_name == "cardcash"


def test_stub_client_fetch_returns_list() -> None:
    import asyncio

    client = _StubClient()
    result = asyncio.run(
        client.fetch_observations(
            merchant_id="target",
            source_key=100,
            observed_at=datetime(2026, 5, 30, tzinfo=UTC),
        )
    )
    assert result == []


def test_stub_client_satisfies_protocol() -> None:
    """Verify _StubClient has all Protocol members (structural check)."""
    client: CompetitorClient = _StubClient()
    assert callable(client.fetch_observations)
    assert isinstance(client.source_name, str)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


def test_error_hierarchy() -> None:
    assert issubclass(CompetitorRateLimitError, CompetitorClientError)
    assert issubclass(CompetitorServerError, CompetitorClientError)
    assert issubclass(CompetitorNetworkError, CompetitorClientError)
    assert issubclass(CompetitorClientError, Exception)


def test_errors_are_raiseable() -> None:
    with pytest.raises(CompetitorClientError):
        raise CompetitorClientError("base error")
    with pytest.raises(CompetitorClientError):
        raise CompetitorRateLimitError("rate limit")
    with pytest.raises(CompetitorClientError):
        raise CompetitorServerError("server error")
    with pytest.raises(CompetitorClientError):
        raise CompetitorNetworkError("network error")


# ---------------------------------------------------------------------------
# Seed: competitor_sources row for cardcash
# ---------------------------------------------------------------------------


def test_seed_creates_cardcash_competitor_source() -> None:
    conn = _make_conn()
    seed_demo_data(conn, BASELINE_FIXTURE)

    row = conn.execute(
        "SELECT source_name, is_active, collection_method, refresh_interval_days, notes "
        "FROM competitor_sources WHERE source_name = 'cardcash'"
    ).fetchone()

    assert row is not None, "cardcash row missing from competitor_sources after seed"
    source_name, is_active, collection_method, refresh_interval_days, notes = row
    assert source_name == "cardcash"
    assert is_active == 1
    assert collection_method == "scraper"
    assert refresh_interval_days == 7
    assert notes is not None and len(notes) > 0
