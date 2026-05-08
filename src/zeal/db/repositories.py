from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

CHANNELS = ("online_sell", "in_mail_buy", "in_store_buy", "electronic_buy")


@dataclass(frozen=True)
class RecommendationSnapshot:
    id: int
    merchant_id: str
    refresh_run_id: int
    online_sell: float | None
    in_mail_buy: float | None
    in_store_buy: float | None
    electronic_buy: float | None
    ebay_sell_pct: float | None
    ebay_confidence: str
    no_data: bool
    formula_breakdown: dict[str, list[dict[str, Any]]]
    config_snapshot: dict[str, Any]
    computed_at: str


@dataclass(frozen=True)
class MerchantListRow:
    merchant_id: str
    display_name: str
    tier: str
    latest: RecommendationSnapshot | None
    delta_last_run: float | None
    delta_last_run_channel: str | None
    max_abs_delta_over_n: float | None
    max_abs_delta_channel: str | None
    last_refresh_status: str | None
    has_live_ebay_observations: bool


@dataclass(frozen=True)
class PricingListSummary:
    active_merchants: int
    last_completed_refresh: str | None
    with_recommendation: int
    no_data: int
    live_ebay_observations: int


@dataclass(frozen=True)
class EbayObservationRow:
    title: str
    sold_at: str
    face_value: float
    sale_price: float
    sell_pct: float | None
    validity_status: str
    exclusion_reason: str | None


@dataclass(frozen=True)
class CompetitorObservationRow:
    source_name: str
    channel: str
    price_pct: float | None
    availability: str
    confidence: str
    observed_at: str
    source_url: str | None


@dataclass(frozen=True)
class RefreshStatusRow:
    refresh_run_id: int
    status: str
    started_at: str
    completed_at: str | None
    has_recommendation: bool


@dataclass(frozen=True)
class MerchantDetailBundle:
    merchant_id: str
    display_name: str
    tier: str
    latest: RecommendationSnapshot | None
    history: list[RecommendationSnapshot]
    recent_ebay_observations: list[EbayObservationRow]
    excluded_ebay_observations: list[EbayObservationRow]
    competitor_observations: list[CompetitorObservationRow]
    recent_refreshes: list[RefreshStatusRow]
    has_live_ebay_observations: bool


def fetch_pricing_list(conn: sqlite3.Connection, *, delta_window: int = 5) -> list[MerchantListRow]:
    merchants = conn.execute(
        """
        SELECT merchant_id, display_name, tier
        FROM merchants
        WHERE is_active = 1
        ORDER BY display_name
        """
    ).fetchall()
    rows = []
    for merchant in merchants:
        history = fetch_recommendation_history(
            conn,
            str(merchant["merchant_id"]),
            limit=max(delta_window + 1, 2),
        )
        latest = history[0] if history else None
        delta_value, delta_channel = delta_from_prior(history)
        max_delta, max_delta_channel = max_absolute_delta_over_window(history, delta_window)
        status = _latest_refresh_status(conn, latest.refresh_run_id if latest else None)
        has_live_observations = _has_live_ebay_observations(
            conn,
            str(merchant["merchant_id"]),
        )
        rows.append(
            MerchantListRow(
                merchant_id=str(merchant["merchant_id"]),
                display_name=str(merchant["display_name"]),
                tier=str(merchant["tier"]),
                latest=latest,
                delta_last_run=delta_value,
                delta_last_run_channel=delta_channel,
                max_abs_delta_over_n=max_delta,
                max_abs_delta_channel=max_delta_channel,
                last_refresh_status=status,
                has_live_ebay_observations=has_live_observations,
            )
        )
    return sorted(
        rows,
        key=lambda row: abs(row.delta_last_run) if row.delta_last_run is not None else -1.0,
        reverse=True,
    )


def fetch_pricing_list_summary(
    conn: sqlite3.Connection,
    rows: list[MerchantListRow],
) -> PricingListSummary:
    last_completed = conn.execute(
        """
        SELECT completed_at
        FROM refresh_runs
        WHERE status IN ('completed', 'partial')
          AND completed_at IS NOT NULL
        ORDER BY completed_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    merchants_with_live_observations = conn.execute(
        """
        SELECT COUNT(DISTINCT eo.merchant_id)
        FROM ebay_observations eo
        JOIN merchants m ON m.merchant_id = eo.merchant_id
        WHERE m.is_active = 1
          AND eo.validity_status = 'valid'
        """
    ).fetchone()[0]
    return PricingListSummary(
        active_merchants=len(rows),
        last_completed_refresh=(
            str(last_completed["completed_at"]) if last_completed is not None else None
        ),
        with_recommendation=sum(
            1 for row in rows if row.latest is not None and not row.latest.no_data
        ),
        no_data=sum(1 for row in rows if row.latest is not None and row.latest.no_data),
        live_ebay_observations=int(merchants_with_live_observations),
    )


def fetch_merchant_detail(
    conn: sqlite3.Connection,
    merchant_id: str,
) -> MerchantDetailBundle | None:
    merchant = conn.execute(
        """
        SELECT merchant_id, display_name, tier
        FROM merchants
        WHERE merchant_id = ?
        """,
        (merchant_id,),
    ).fetchone()
    if merchant is None:
        return None
    history = fetch_recommendation_history(conn, merchant_id, limit=90)
    return MerchantDetailBundle(
        merchant_id=str(merchant["merchant_id"]),
        display_name=str(merchant["display_name"]),
        tier=str(merchant["tier"]),
        latest=history[0] if history else None,
        history=history,
        recent_ebay_observations=_fetch_ebay_observations(conn, merchant_id, "valid"),
        excluded_ebay_observations=_fetch_ebay_observations(conn, merchant_id, "excluded"),
        competitor_observations=_fetch_competitor_observations(conn, merchant_id),
        recent_refreshes=_fetch_recent_refreshes(conn, merchant_id),
        has_live_ebay_observations=_has_live_ebay_observations(conn, merchant_id),
    )


def fetch_recommendation_history(
    conn: sqlite3.Connection,
    merchant_id: str,
    *,
    limit: int = 90,
) -> list[RecommendationSnapshot]:
    records = conn.execute(
        """
        SELECT *
        FROM price_recommendations
        WHERE merchant_id = ?
        ORDER BY computed_at DESC, id DESC
        LIMIT ?
        """,
        (merchant_id, limit),
    ).fetchall()
    return [_recommendation_from_row(record) for record in records]


def delta_from_prior(
    history_desc: list[RecommendationSnapshot],
) -> tuple[float | None, str | None]:
    if len(history_desc) < 2:
        return None, None
    latest = history_desc[0]
    prior = history_desc[1]
    return _largest_channel_delta(latest, prior)


def max_absolute_delta_over_window(
    history_desc: list[RecommendationSnapshot],
    window: int,
) -> tuple[float | None, str | None]:
    if len(history_desc) < 2:
        return None, None
    best_delta: float | None = None
    best_channel: str | None = None
    pairs = list(zip(history_desc, history_desc[1:], strict=False))[:window]
    for latest, prior in pairs:
        delta, channel = _largest_channel_delta(latest, prior)
        if delta is None or channel is None:
            continue
        if best_delta is None or abs(delta) > abs(best_delta):
            best_delta = delta
            best_channel = channel
    return best_delta, best_channel


def _largest_channel_delta(
    latest: RecommendationSnapshot,
    prior: RecommendationSnapshot,
) -> tuple[float | None, str | None]:
    best_delta: float | None = None
    best_channel: str | None = None
    for channel in CHANNELS:
        latest_value = getattr(latest, channel)
        prior_value = getattr(prior, channel)
        if latest_value is None or prior_value is None:
            continue
        delta = latest_value - prior_value
        if best_delta is None or abs(delta) > abs(best_delta):
            best_delta = delta
            best_channel = channel
    return best_delta, best_channel


def _recommendation_from_row(row: sqlite3.Row) -> RecommendationSnapshot:
    return RecommendationSnapshot(
        id=int(row["id"]),
        merchant_id=str(row["merchant_id"]),
        refresh_run_id=int(row["refresh_run_id"]),
        online_sell=_optional_float(row["online_sell"]),
        in_mail_buy=_optional_float(row["in_mail_buy"]),
        in_store_buy=_optional_float(row["in_store_buy"]),
        electronic_buy=_optional_float(row["electronic_buy"]),
        ebay_sell_pct=_optional_float(row["ebay_sell_pct"]),
        ebay_confidence=str(row["ebay_confidence"]),
        no_data=bool(row["no_data"]),
        formula_breakdown=json.loads(str(row["formula_breakdown_json"])),
        config_snapshot=json.loads(str(row["config_snapshot_json"])),
        computed_at=str(row["computed_at"]),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float | str):
        return float(value)
    raise TypeError(f"Expected numeric SQLite value, got {type(value).__name__}")


def _latest_refresh_status(conn: sqlite3.Connection, refresh_run_id: int | None) -> str | None:
    if refresh_run_id is None:
        return None
    row = conn.execute("SELECT status FROM refresh_runs WHERE id = ?", (refresh_run_id,)).fetchone()
    return str(row["status"]) if row is not None else None


def _has_live_ebay_observations(conn: sqlite3.Connection, merchant_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM ebay_observations
        WHERE merchant_id = ?
          AND validity_status = 'valid'
        LIMIT 1
        """,
        (merchant_id,),
    ).fetchone()
    return row is not None


def _fetch_ebay_observations(
    conn: sqlite3.Connection,
    merchant_id: str,
    validity_status: str,
) -> list[EbayObservationRow]:
    records = conn.execute(
        """
        SELECT title, sold_at, face_value, sale_price, validity_status, exclusion_reason
        FROM ebay_observations
        WHERE merchant_id = ? AND validity_status = ?
        ORDER BY sold_at DESC
        LIMIT 30
        """,
        (merchant_id, validity_status),
    ).fetchall()
    return [
        EbayObservationRow(
            title=str(row["title"]),
            sold_at=str(row["sold_at"]),
            face_value=float(row["face_value"]),
            sale_price=float(row["sale_price"]),
            sell_pct=_safe_sell_pct(row["sale_price"], row["face_value"]),
            validity_status=str(row["validity_status"]),
            exclusion_reason=(
                str(row["exclusion_reason"]) if row["exclusion_reason"] is not None else None
            ),
        )
        for row in records
    ]


def _safe_sell_pct(sale_price: Any, face_value: Any) -> float | None:
    face = float(face_value)
    if face <= 0:
        return None
    return float(sale_price) / face


def _fetch_competitor_observations(
    conn: sqlite3.Connection,
    merchant_id: str,
) -> list[CompetitorObservationRow]:
    records = conn.execute(
        """
        SELECT source_name, channel, price_pct, availability, confidence, observed_at, source_url
        FROM competitor_observations
        WHERE merchant_id = ?
        ORDER BY observed_at DESC
        LIMIT 20
        """,
        (merchant_id,),
    ).fetchall()
    return [
        CompetitorObservationRow(
            source_name=str(row["source_name"]),
            channel=str(row["channel"]),
            price_pct=_optional_float(row["price_pct"]),
            availability=str(row["availability"]),
            confidence=str(row["confidence"]),
            observed_at=str(row["observed_at"]),
            source_url=str(row["source_url"]) if row["source_url"] is not None else None,
        )
        for row in records
    ]


def _fetch_recent_refreshes(
    conn: sqlite3.Connection,
    merchant_id: str,
) -> list[RefreshStatusRow]:
    records = conn.execute(
        """
        SELECT
            rr.id,
            rr.status,
            rr.started_at,
            rr.completed_at,
            pr.id AS recommendation_id
        FROM refresh_runs rr
        LEFT JOIN price_recommendations pr
            ON pr.refresh_run_id = rr.id
            AND pr.merchant_id = ?
        ORDER BY rr.started_at DESC, rr.id DESC
        LIMIT 10
        """,
        (merchant_id,),
    ).fetchall()
    return [
        RefreshStatusRow(
            refresh_run_id=int(row["id"]),
            status=str(row["status"]),
            started_at=str(row["started_at"]),
            completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
            has_recommendation=row["recommendation_id"] is not None,
        )
        for row in records
    ]
