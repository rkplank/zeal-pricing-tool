from datetime import UTC, datetime

import pytest

from zeal.models.competitor import CompetitorObservation
from zeal.pricing.competitor_aggregate import aggregate_competitor_observations


def _obs(
    source_name: str,
    channel: str,
    price_pct: float | None,
    confidence: str,
    observed_at: str,
    availability: str = "available",
) -> CompetitorObservation:
    return CompetitorObservation(
        merchant_id="target",
        source_name=source_name,
        channel=channel,  # type: ignore[arg-type]
        price_pct=price_pct,
        availability=availability,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        observed_at=observed_at,
    )


def test_uses_latest_valid_observation_per_source_channel() -> None:
    aggregate = aggregate_competitor_observations(
        [
            _obs("cardcash", "buy_mail", 0.70, "high", "2026-04-10T00:00:00Z"),
            _obs("cardcash", "buy_mail", 0.74, "high", "2026-05-01T00:00:00Z"),
        ],
        merchant_id="target",
        as_of=datetime(2026, 5, 4, tzinfo=UTC),
    )
    assert aggregate.in_mail_buy == pytest.approx(0.74)
    assert aggregate.sources_contributing == ("cardcash",)


def test_cross_source_weighted_average() -> None:
    aggregate = aggregate_competitor_observations(
        [
            _obs("cardcash", "buy_mail", 0.74, "high", "2026-05-01T00:00:00Z"),
            _obs("manual", "buy_mail", 0.70, "medium", "2026-05-02T00:00:00Z"),
        ],
        merchant_id="target",
        as_of=datetime(2026, 5, 4, tzinfo=UTC),
    )
    assert aggregate.in_mail_buy == pytest.approx((0.74 + 0.5 * 0.70) / 1.5)


def test_invalid_observations_are_excluded() -> None:
    aggregate = aggregate_competitor_observations(
        [
            _obs("old", "buy_mail", 0.74, "high", "2026-03-01T00:00:00Z"),
            _obs("none", "buy_mail", 0.75, "none", "2026-05-01T00:00:00Z"),
            _obs("bad_price", "buy_mail", 1.30, "high", "2026-05-01T00:00:00Z"),
            _obs("unavailable", "buy_mail", 0.70, "high", "2026-05-01T00:00:00Z", "unavailable"),
        ],
        merchant_id="target",
        as_of=datetime(2026, 5, 4, tzinfo=UTC),
    )
    assert aggregate.in_mail_buy is None
    assert aggregate.sources_contributing == ()
