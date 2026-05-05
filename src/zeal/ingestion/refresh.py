from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from zeal.ingestion.ebay_client import EbayClient


@dataclass(frozen=True)
class RefreshProgress:
    run_id: int
    processed: int
    total: int
    status: str


async def collect_sold_listings(
    conn: sqlite3.Connection,
    ebay_client: EbayClient,
) -> RefreshProgress:
    """Phase 3 seam: call an injected eBay client for active merchants.

    Phase 2 does not wire this into the UI or call a live client. The function exists so the
    future refresh route depends on an interface instead of hardcoded API calls.
    """

    run_id = conn.execute(
        """
        INSERT INTO refresh_runs (status, total)
        SELECT 'running', COUNT(*) FROM merchants WHERE is_active = 1
        RETURNING id
        """
    ).fetchone()[0]

    merchants = conn.execute(
        """
        SELECT merchant_id, inclusion_regex, exclusion_regex
        FROM merchants
        WHERE is_active = 1
        ORDER BY display_name
        """
    ).fetchall()
    processed = 0
    for merchant in merchants:
        listings = await ebay_client.sold_listings_for_merchant(
            merchant_id=str(merchant["merchant_id"]),
            inclusion_regex=str(merchant["inclusion_regex"]),
            exclusion_regex=merchant["exclusion_regex"],
        )
        for listing in listings:
            conn.execute(
                """
                INSERT OR IGNORE INTO ebay_observations (
                    merchant_id, listing_id, sold_at, face_value, sale_price,
                    title, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    merchant["merchant_id"],
                    listing.listing_id,
                    listing.sold_at,
                    listing.face_value,
                    listing.sale_price,
                    listing.title,
                    listing.raw_payload,
                ),
            )
        processed += 1
        conn.execute(
            "UPDATE refresh_runs SET processed = ? WHERE id = ?",
            (processed, run_id),
        )

    conn.execute(
        """
        UPDATE refresh_runs
        SET status = 'completed', completed_at = datetime('now')
        WHERE id = ?
        """,
        (run_id,),
    )
    conn.commit()
    return RefreshProgress(
        run_id=run_id,
        processed=processed,
        total=len(merchants),
        status="completed",
    )
