"""End-to-end tests for the refresh orchestrator against an in-memory DB."""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import pytest

from zeal.db.connection import apply_schema
from zeal.db.seed import DEMO_CONSTANTS
from zeal.ingestion.ebay_client import EbaySoldListing, SyntheticEbayClient
from zeal.ingestion.refresh import RefreshSummary, run_refresh
from zeal.models.pricing import GlobalConstants

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 6, 1, 12, 0, 0)
_RECENT = (_NOW - timedelta(days=5)).isoformat()


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return conn


def _seed_merchant(
    conn: sqlite3.Connection,
    merchant_id: str,
    display_name: str,
    *,
    is_active: bool = True,
    online_sell_override: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO merchants (
            merchant_id, display_name, tier,
            in_store_margin, in_mail_margin, e_bonus, ebay_differential,
            in_store_eligible, in_mail_eligible, electronic_eligible,
            merch_credit_variant, inclusion_regex, is_active,
            online_sell_override, ebay_weight
        ) VALUES (?, ?, 'C', 0.25, 0.07, 0.08, 0.045, 1, 1, 1, 0, ?, ?, ?, 1.0)
        """,
        (
            merchant_id,
            display_name,
            display_name.lower(),  # inclusion_regex
            int(is_active),
            online_sell_override,
        ),
    )
    conn.commit()


def _make_listing(
    merchant_id: str,
    listing_id: str = "lid-1",
    sold_at: str = _RECENT,
    face_value: float = 100.0,
    sale_price: float = 85.0,
) -> EbaySoldListing:
    return EbaySoldListing(
        listing_id=listing_id,
        sold_at=sold_at,
        face_value=face_value,
        sale_price=sale_price,
        title=f"{merchant_id} gift card",
        raw_payload=f'{{"itemId": "{listing_id}"}}',
    )


def _listings_for(
    merchant_id: str, n: int = 3
) -> list[EbaySoldListing]:
    return [
        _make_listing(merchant_id, listing_id=f"lid-{merchant_id}-{i}")
        for i in range(n)
    ]


async def _run(
    db: sqlite3.Connection,
    client: Any,
    constants: GlobalConstants = DEMO_CONSTANTS,
    progress_hook: Any = None,
) -> RefreshSummary:
    return await run_refresh(
        db=db,
        ebay_client=client,
        constants=constants,
        progress_hook=progress_hook,
        now=_NOW,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_three_merchants() -> None:
    conn = _make_db()
    for mid in ("alpha", "beta", "gamma"):
        _seed_merchant(conn, mid, mid.title())
    client = SyntheticEbayClient({mid: _listings_for(mid) for mid in ("alpha", "beta", "gamma")})

    summary = await _run(conn, client)

    assert summary.status == "completed"
    assert summary.processed == 3
    assert summary.total == 3
    assert summary.errored_merchants == []

    run_row = conn.execute(
        "SELECT * FROM refresh_runs WHERE id = ?", (summary.refresh_run_id,)
    ).fetchone()
    assert run_row["status"] == "completed"
    assert run_row["processed"] == 3

    assert conn.execute("SELECT COUNT(*) FROM ebay_summary").fetchone()[0] == 3
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM price_recommendations WHERE refresh_run_id = ?",
            (summary.refresh_run_id,),
        ).fetchone()[0]
        == 3
    )


# ---------------------------------------------------------------------------
# Per-merchant failure → partial
# ---------------------------------------------------------------------------


class _ErrorClient:
    """Client that raises for specific merchant IDs, delegates rest to inner."""

    def __init__(
        self,
        inner: SyntheticEbayClient,
        errors: dict[str, Exception],
    ) -> None:
        self._inner = inner
        self._errors = errors

    async def sold_listings_for_merchant(
        self,
        *,
        merchant_id: str,
        inclusion_regex: str,
        exclusion_regex: str | None,
    ) -> Sequence[EbaySoldListing]:
        if merchant_id in self._errors:
            raise self._errors[merchant_id]
        return await self._inner.sold_listings_for_merchant(
            merchant_id=merchant_id,
            inclusion_regex=inclusion_regex,
            exclusion_regex=exclusion_regex,
        )


@pytest.mark.asyncio
async def test_per_merchant_failure_yields_partial() -> None:
    conn = _make_db()
    for mid in ("alpha", "beta", "gamma"):
        _seed_merchant(conn, mid, mid.title())
    inner = SyntheticEbayClient({mid: _listings_for(mid) for mid in ("alpha", "beta", "gamma")})
    client = _ErrorClient(inner, {"beta": RuntimeError("eBay timeout")})

    summary = await _run(conn, client)

    assert summary.status == "partial"
    assert summary.processed == 3
    assert summary.errored_merchants == ["beta"]

    run_row = conn.execute(
        "SELECT * FROM refresh_runs WHERE id = ?", (summary.refresh_run_id,)
    ).fetchone()
    assert run_row["status"] == "partial"
    assert "1 merchants errored" in run_row["error"]

    # alpha and gamma got recommendations; beta did not
    recs = conn.execute(
        "SELECT merchant_id FROM price_recommendations WHERE refresh_run_id = ?",
        (summary.refresh_run_id,),
    ).fetchall()
    rec_ids = {r["merchant_id"] for r in recs}
    assert rec_ids == {"alpha", "gamma"}


# ---------------------------------------------------------------------------
# Override merchant skips eBay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_override_merchant() -> None:
    conn = _make_db()
    _seed_merchant(conn, "override_m", "Override M", online_sell_override=0.80)
    _seed_merchant(conn, "normal_m", "Normal M")

    call_log: list[str] = []

    class _TrackingClient:
        async def sold_listings_for_merchant(
            self, *, merchant_id: str, **_: object
        ) -> Sequence[EbaySoldListing]:
            call_log.append(merchant_id)
            return _listings_for(merchant_id)

    summary = await _run(conn, _TrackingClient())

    assert summary.skipped_override_merchants == ["override_m"]
    # eBay was only called for the normal merchant
    assert "override_m" not in call_log
    assert "normal_m" in call_log

    # override merchant produces a recommendation but zero observations
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM price_recommendations WHERE merchant_id = 'override_m'"
        ).fetchone()[0]
        == 1
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM ebay_observations WHERE merchant_id = 'override_m'"
        ).fetchone()[0]
        == 0
    )


# ---------------------------------------------------------------------------
# Progress hook receives correct call sequence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_hook_call_sequence() -> None:
    conn = _make_db()
    for mid in ("alpha", "beta", "gamma"):
        _seed_merchant(conn, mid, mid.title())
    client = SyntheticEbayClient({mid: _listings_for(mid) for mid in ("alpha", "beta", "gamma")})

    calls: list[tuple[int, int]] = []

    async def hook(processed: int, total: int) -> None:
        calls.append((processed, total))

    await _run(conn, client, progress_hook=hook)

    assert calls == [(1, 3), (2, 3), (3, 3)]


# ---------------------------------------------------------------------------
# Multiple refreshes: append-only recommendations, no duplicate observations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_refreshes_append_only() -> None:
    conn = _make_db()
    _seed_merchant(conn, "target", "Target")
    # Both runs return the same listing_id to test UPSERT idempotency.
    listings = [_make_listing("target", listing_id="lid-shared")]
    client = SyntheticEbayClient({"target": listings})

    summary1 = await _run(conn, client)
    summary2 = await _run(conn, client)

    assert summary1.refresh_run_id != summary2.refresh_run_id
    assert conn.execute("SELECT COUNT(*) FROM refresh_runs").fetchone()[0] == 2
    # Two recommendations (one per run), one observation (deduped by listing_id).
    assert conn.execute("SELECT COUNT(*) FROM price_recommendations").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM ebay_observations").fetchone()[0] == 1
    raw_payload = conn.execute(
        "SELECT raw_payload FROM ebay_observations WHERE listing_id = 'lid-shared'"
    ).fetchone()["raw_payload"]
    assert raw_payload == '{"itemId": "lid-shared"}'


@pytest.mark.asyncio
async def test_repeated_listing_updates_validity_status() -> None:
    conn = _make_db()
    _seed_merchant(conn, "target", "Target")

    class _ChangingClient:
        def __init__(self) -> None:
            self.calls = 0

        async def sold_listings_for_merchant(
            self,
            *,
            merchant_id: str,
            inclusion_regex: str,
            exclusion_regex: str | None,
        ) -> Sequence[EbaySoldListing]:
            _ = (inclusion_regex, exclusion_regex)
            self.calls += 1
            if self.calls == 1:
                return [
                    _make_listing(
                        merchant_id,
                        listing_id="lid-shared",
                        face_value=0.0,
                        sale_price=85.0,
                    )
                ]
            return [
                _make_listing(
                    merchant_id,
                    listing_id="lid-shared",
                    face_value=100.0,
                    sale_price=85.0,
                )
            ]

    client = _ChangingClient()

    await _run(conn, client)
    first = conn.execute(
        "SELECT validity_status, exclusion_reason FROM ebay_observations"
    ).fetchone()
    assert first["validity_status"] == "excluded"
    assert first["exclusion_reason"] == "zero_or_negative_face_value"

    await _run(conn, client)
    second = conn.execute(
        "SELECT validity_status, exclusion_reason FROM ebay_observations"
    ).fetchone()
    assert second["validity_status"] == "valid"
    assert second["exclusion_reason"] is None


# ---------------------------------------------------------------------------
# Empty active-merchant set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_merchant_set() -> None:
    conn = _make_db()
    client = SyntheticEbayClient({})

    summary = await _run(conn, client)

    assert summary.status == "completed"
    assert summary.processed == 0
    assert summary.total == 0
    assert summary.errored_merchants == []
    assert conn.execute("SELECT COUNT(*) FROM price_recommendations").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Inactive merchants are skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inactive_merchant_not_processed() -> None:
    conn = _make_db()
    _seed_merchant(conn, "active_m", "Active M")
    _seed_merchant(conn, "inactive_m", "Inactive M", is_active=False)
    client = SyntheticEbayClient(
        {"active_m": _listings_for("active_m"), "inactive_m": _listings_for("inactive_m")}
    )

    summary = await _run(conn, client)

    assert summary.processed == 1
    assert summary.total == 1
    assert "inactive_m" not in summary.skipped_override_merchants
    assert "inactive_m" not in summary.errored_merchants
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM price_recommendations WHERE merchant_id = 'inactive_m'"
        ).fetchone()[0]
        == 0
    )


# ---------------------------------------------------------------------------
# Catastrophic failure marks run as 'failed'
# ---------------------------------------------------------------------------


class _FailAfterN:
    """Thin connection wrapper that raises OperationalError on the Nth match."""

    def __init__(self, conn: sqlite3.Connection, pattern: str, fail_after: int) -> None:
        self._conn = conn
        self._pattern = pattern
        self._count = 0
        self._fail_after = fail_after

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any:
        if self._pattern in sql:
            self._count += 1
            if self._count > self._fail_after:
                raise sqlite3.OperationalError("simulated catastrophic DB error")
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


@pytest.mark.asyncio
async def test_catastrophic_failure_marks_run_failed() -> None:
    real_conn = _make_db()
    for mid in ("alpha", "beta"):
        _seed_merchant(real_conn, mid, mid.title())
    client = SyntheticEbayClient({mid: _listings_for(mid) for mid in ("alpha", "beta")})

    # Fail on the second "UPDATE refresh_runs SET processed" (after alpha succeeds).
    wrapped = _FailAfterN(real_conn, "UPDATE refresh_runs SET processed", fail_after=1)

    with pytest.raises(sqlite3.OperationalError, match="simulated catastrophic"):
        await run_refresh(
            db=wrapped,  # type: ignore[arg-type]
            ebay_client=client,
            constants=DEMO_CONSTANTS,
            now=_NOW,
        )

    run_row = real_conn.execute("SELECT status, error FROM refresh_runs").fetchone()
    assert run_row["status"] == "failed"
    assert run_row["error"] is not None
