from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from zeal.db.repositories import get_merchants_for_competitor_refresh
from zeal.ingestion.competitor.base import CompetitorClient
from zeal.ingestion.competitor.errors import CompetitorClientError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompetitorRefreshSummary:
    refresh_run_id: int
    status: Literal["completed", "partial", "failed"]
    processed: int
    total: int
    errored_merchants: list[str]


async def run_competitor_refresh(
    *,
    db: sqlite3.Connection,
    client: CompetitorClient,
    now: datetime | None = None,
    limit: int | None = None,
) -> CompetitorRefreshSummary:
    _now = now if now is not None else datetime.now(UTC)
    ts = _as_naive_utc(_now).isoformat()

    merchants = get_merchants_for_competitor_refresh(db)
    if limit is not None:
        merchants = merchants[:limit]
    total = len(merchants)

    run_id = db.execute(
        """
        INSERT INTO refresh_runs (kind, status, started_at, total, processed)
        VALUES ('competitor', 'running', ?, ?, 0)
        RETURNING id
        """,
        (ts, total),
    ).fetchone()[0]
    db.commit()

    errored: list[str] = []
    processed = 0

    try:
        for merchant in merchants:
            merchant_id = merchant.merchant_id
            try:
                observations = await client.fetch_observations(
                    merchant_id=merchant_id,
                    source_key=merchant.cardcash_id,
                    observed_at=_now,
                )
                for obs in observations:
                    db.execute(
                        """
                        INSERT INTO competitor_observations
                            (source_name, merchant_id, channel, price_pct, availability,
                             confidence, observed_at, source_url, raw_payload)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            obs.source_name,
                            obs.merchant_id,
                            obs.channel,
                            obs.price_pct,
                            obs.availability,
                            obs.confidence,
                            obs.observed_at,
                            obs.source_url,
                            obs.raw_payload,
                        ),
                    )
            except CompetitorClientError:
                raise
            except Exception:
                logger.exception(
                    "Merchant %s failed during competitor refresh run %d", merchant_id, run_id
                )
                errored.append(merchant_id)

            processed += 1
            db.execute(
                "UPDATE refresh_runs SET processed = ? WHERE id = ?",
                (processed, run_id),
            )

        status: Literal["completed", "partial", "failed"] = (
            "completed" if not errored else "partial"
        )
        error_msg: str | None = f"{len(errored)} merchants errored" if errored else None
        db.execute(
            """
            UPDATE refresh_runs
            SET status = ?, completed_at = ?, error = ?
            WHERE id = ?
            """,
            (status, ts, error_msg, run_id),
        )
        db.execute(
            """
            UPDATE competitor_sources
            SET last_attempted_refresh = ?, last_successful_refresh = ?
            WHERE source_name = ?
            """,
            (ts, ts, client.source_name),
        )
        db.commit()
        return CompetitorRefreshSummary(
            refresh_run_id=run_id,
            status=status,
            processed=processed,
            total=total,
            errored_merchants=errored,
        )

    except CompetitorClientError as exc:
        try:
            db.execute(
                """
                UPDATE refresh_runs
                SET status = 'failed', completed_at = ?, processed = ?, error = ?
                WHERE id = ?
                """,
                (ts, processed, str(exc), run_id),
            )
            db.execute(
                """
                UPDATE competitor_sources
                SET last_attempted_refresh = ?
                WHERE source_name = ?
                """,
                (ts, client.source_name),
            )
            db.commit()
        except Exception:
            logger.exception("Could not mark competitor refresh run %d as failed", run_id)
        return CompetitorRefreshSummary(
            refresh_run_id=run_id,
            status="failed",
            processed=processed,
            total=total,
            errored_merchants=errored,
        )


def _as_naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
