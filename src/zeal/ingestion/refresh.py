from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from zeal.ingestion.ebay_client import EbayClient
from zeal.models.ebay import EbayObservation, EbaySoldListing
from zeal.models.merchant import MerchantRecord
from zeal.models.pricing import CompetitorAggregate, GlobalConstants
from zeal.pricing.confidence import score_confidence
from zeal.pricing.ebay_average import compute_ebay_average
from zeal.pricing.engine import compute_prices
from zeal.pricing.listing_filter import filter_listings

logger = logging.getLogger(__name__)

_MAX_FETCH = 50
_MAX_VALID = 10


@dataclass(frozen=True)
class RefreshSummary:
    refresh_run_id: int
    status: Literal["completed", "partial", "failed"]
    processed: int
    total: int
    errored_merchants: list[str]
    skipped_override_merchants: list[str]


async def run_refresh(
    *,
    db: sqlite3.Connection,
    ebay_client: EbayClient,
    constants: GlobalConstants,
    progress_hook: Callable[[int, int], Awaitable[None]] | None = None,
    now: datetime | None = None,
) -> RefreshSummary:
    _now = now if now is not None else datetime.now(UTC)
    today = _as_naive_utc(_now).strftime("%Y-%m-%d")

    merchant_rows = db.execute(
        "SELECT * FROM merchants WHERE is_active = 1 ORDER BY merchant_id ASC"
    ).fetchall()
    total = len(merchant_rows)

    run_id = db.execute(
        """
        INSERT INTO refresh_runs (status, started_at, total, processed)
        VALUES ('running', ?, ?, 0)
        RETURNING id
        """,
        (_as_naive_utc(_now).isoformat(), total),
    ).fetchone()[0]
    db.commit()

    errored: list[str] = []
    skipped_override: list[str] = []
    processed = 0

    try:
        for row in merchant_rows:
            merchant = _row_to_merchant(row)
            merchant_id = merchant.merchant_id

            try:
                if merchant.online_sell_override is not None:
                    _process_override(db, run_id, merchant, constants, _now)
                    skipped_override.append(merchant_id)
                else:
                    await _process_ebay(
                        db, run_id, merchant, ebay_client, constants, _now, today
                    )
            except Exception:
                logger.exception(
                    "Merchant %s failed during refresh run %d", merchant_id, run_id
                )
                errored.append(merchant_id)

            processed += 1
            # NOTE: outside per-merchant try — a failure here is catastrophic.
            db.execute(
                "UPDATE refresh_runs SET processed = ? WHERE id = ?",
                (processed, run_id),
            )
            if progress_hook is not None:
                await progress_hook(processed, total)

        status: Literal["completed", "partial", "failed"] = (
            "completed" if not errored else "partial"
        )
        error_msg: str | None = (
            f"{len(errored)} merchants errored" if errored else None
        )
        db.execute(
            """
            UPDATE refresh_runs
            SET status = ?, completed_at = ?, error = ?
            WHERE id = ?
            """,
            (status, _as_naive_utc(_now).isoformat(), error_msg, run_id),
        )
        db.commit()
        return RefreshSummary(
            refresh_run_id=run_id,
            status=status,
            processed=processed,
            total=total,
            errored_merchants=errored,
            skipped_override_merchants=skipped_override,
        )

    except Exception as exc:
        try:
            db.execute(
                """
                UPDATE refresh_runs
                SET status = 'failed', completed_at = ?, processed = ?, error = ?
                WHERE id = ?
                """,
                (_as_naive_utc(_now).isoformat(), processed, str(exc), run_id),
            )
            db.commit()
        except Exception:
            logger.exception("Could not mark refresh run %d as failed", run_id)
        raise


# ---------------------------------------------------------------------------
# Per-merchant helpers
# ---------------------------------------------------------------------------


def _process_override(
    db: sqlite3.Connection,
    run_id: int,
    merchant: MerchantRecord,
    constants: GlobalConstants,
    now: datetime,
) -> None:
    rec = compute_prices(None, "none", CompetitorAggregate(), merchant, constants)
    _insert_recommendation(db, run_id, merchant, rec, None, "none", now)


async def _process_ebay(
    db: sqlite3.Connection,
    run_id: int,
    merchant: MerchantRecord,
    ebay_client: EbayClient,
    constants: GlobalConstants,
    now: datetime,
    today: str,
) -> None:
    raw = await ebay_client.sold_listings_for_merchant(
        merchant_id=merchant.merchant_id,
        inclusion_regex=merchant.inclusion_regex,
        exclusion_regex=merchant.exclusion_regex,
    )

    filter_result = filter_listings(raw, merchant, now=now)

    excluded_map = {e.listing.listing_id: e.exclusion_reason for e in filter_result.excluded}
    _persist_observations(db, merchant.merchant_id, raw, excluded_map)

    valid_recent = sorted(filter_result.valid, key=lambda lst: lst.sold_at, reverse=True)[
        :_MAX_VALID
    ]
    observations = [_listing_to_observation(merchant.merchant_id, lst) for lst in valid_recent]

    ebay_sell_pct = compute_ebay_average(observations)
    sample_size = len(observations)
    most_recent_obs: str | None = None
    age_days: int | None = None
    if observations:
        most_recent_obs = max(o.sold_at for o in observations)
        sold_dt = datetime.fromisoformat(most_recent_obs).replace(tzinfo=None)
        age_days = (_as_naive_utc(now) - sold_dt).days

    ebay_confidence = score_confidence(sample_size, age_days)

    db.execute(
        """
        INSERT OR REPLACE INTO ebay_summary
            (merchant_id, summary_date, ebay_sell_pct, sample_size,
             most_recent_observation, confidence)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (merchant.merchant_id, today, ebay_sell_pct, sample_size, most_recent_obs, ebay_confidence),
    )

    rec = compute_prices(ebay_sell_pct, ebay_confidence, CompetitorAggregate(), merchant, constants)
    _insert_recommendation(db, run_id, merchant, rec, ebay_sell_pct, ebay_confidence, now)


def _persist_observations(
    db: sqlite3.Connection,
    merchant_id: str,
    listings: Sequence[EbaySoldListing],
    excluded_map: Mapping[str, str | None],
) -> None:
    for listing in listings:
        exclusion_reason = excluded_map.get(listing.listing_id)
        validity_status = "excluded" if listing.listing_id in excluded_map else "valid"
        db.execute(
            """
            INSERT OR IGNORE INTO ebay_observations
                (merchant_id, listing_id, sold_at, face_value, sale_price,
                 title, validity_status, exclusion_reason, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merchant_id,
                listing.listing_id,
                listing.sold_at,
                listing.face_value,
                listing.sale_price,
                listing.title,
                validity_status,
                exclusion_reason,
                listing.raw_payload,
            ),
        )


def _insert_recommendation(
    db: sqlite3.Connection,
    run_id: int,
    merchant: MerchantRecord,
    rec: object,
    ebay_sell_pct: float | None,
    ebay_confidence: str,
    now: datetime,
) -> None:
    from zeal.models.pricing import PriceRecommendation

    assert isinstance(rec, PriceRecommendation)
    channels = ("online_sell", "in_mail_buy", "in_store_buy", "electronic_buy")
    breakdown = {
        ch: [s.model_dump() for s in getattr(rec, ch).breakdown] for ch in channels
    }
    db.execute(
        """
        INSERT INTO price_recommendations
            (merchant_id, refresh_run_id,
             online_sell, in_mail_buy, in_store_buy, electronic_buy,
             ebay_sell_pct, ebay_confidence, no_data,
             formula_breakdown_json, config_snapshot_json, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            merchant.merchant_id,
            run_id,
            _num(rec.online_sell.final_value),
            _num(rec.in_mail_buy.final_value),
            _num(rec.in_store_buy.final_value),
            _num(rec.electronic_buy.final_value),
            ebay_sell_pct,
            ebay_confidence,
            int(rec.no_data),
            json.dumps(breakdown, sort_keys=True),
            merchant.model_dump_json(),
            _as_naive_utc(now).isoformat(),
        ),
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _row_to_merchant(row: sqlite3.Row) -> MerchantRecord:
    return MerchantRecord(
        merchant_id=str(row["merchant_id"]),
        display_name=str(row["display_name"]),
        tier=str(row["tier"]),
        in_store_margin=float(row["in_store_margin"]),
        in_mail_margin=float(row["in_mail_margin"]),
        e_bonus=float(row["e_bonus"]) if row["e_bonus"] is not None else None,
        ebay_differential=float(row["ebay_differential"]),
        in_store_eligible=bool(row["in_store_eligible"]),
        in_mail_eligible=bool(row["in_mail_eligible"]),
        electronic_eligible=bool(row["electronic_eligible"]),
        online_sell_override=(
            float(row["online_sell_override"])
            if row["online_sell_override"] is not None
            else None
        ),
        electronic_buy_override=(
            float(row["electronic_buy_override"])
            if row["electronic_buy_override"] is not None
            else None
        ),
        ebay_weight=float(row["ebay_weight"]),
        merch_credit_variant=bool(row["merch_credit_variant"]),
        inclusion_regex=str(row["inclusion_regex"]),
        exclusion_regex=(
            str(row["exclusion_regex"]) if row["exclusion_regex"] is not None else None
        ),
        notes=str(row["notes"]) if row["notes"] is not None else None,
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _listing_to_observation(merchant_id: str, listing: EbaySoldListing) -> EbayObservation:
    return EbayObservation(
        merchant_id=merchant_id,
        listing_id=listing.listing_id,
        sold_at=listing.sold_at,
        face_value=listing.face_value,
        sale_price=listing.sale_price,
        title=listing.title,
    )


def _as_naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _num(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None
