from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from zeal.models.competitor import CompetitorObservation
from zeal.models.pricing import CompetitorAggregate

_WEIGHTS = {"high": 1.0, "medium": 0.5, "low": 0.25}
_CHANNEL_TO_FIELD = {
    "sell": "online_sell",
    "marketplace_sell": "online_sell",
    "buy_mail": "in_mail_buy",
    "buy_electronic": "electronic_buy",
}


def aggregate_competitor_observations(
    observations: Iterable[CompetitorObservation],
    *,
    merchant_id: str,
    as_of: datetime | None = None,
    max_age_days: int = 30,
) -> CompetitorAggregate:
    as_of = as_of or datetime.now(UTC)
    cutoff = as_of - timedelta(days=max_age_days)

    latest_by_source_channel: dict[tuple[str, str], CompetitorObservation] = {}
    for observation in observations:
        if observation.merchant_id != merchant_id or not _is_valid(observation):
            continue
        observed_at = _parse_datetime(observation.observed_at)
        if observed_at < cutoff or observed_at > as_of:
            continue
        key = (observation.source_name, observation.channel)
        current = latest_by_source_channel.get(key)
        if current is None or observed_at > _parse_datetime(current.observed_at):
            latest_by_source_channel[key] = observation

    values_by_field: dict[str, list[tuple[float, float, str]]] = {}
    for observation in latest_by_source_channel.values():
        field = _CHANNEL_TO_FIELD[observation.channel]
        assert observation.price_pct is not None
        values_by_field.setdefault(field, []).append(
            (_WEIGHTS[observation.confidence], observation.price_pct, observation.source_name)
        )

    sources = tuple(
        sorted({source for values in values_by_field.values() for _, _, source in values})
    )
    return CompetitorAggregate(
        online_sell=_weighted_average(values_by_field.get("online_sell", [])),
        in_mail_buy=_weighted_average(values_by_field.get("in_mail_buy", [])),
        electronic_buy=_weighted_average(values_by_field.get("electronic_buy", [])),
        sources_contributing=sources,
    )


def _is_valid(observation: CompetitorObservation) -> bool:
    return (
        observation.availability == "available"
        and observation.confidence != "none"
        and observation.price_pct is not None
        and 0.20 <= observation.price_pct <= 1.20
    )


def _weighted_average(values: list[tuple[float, float, str]]) -> float | None:
    if not values:
        return None
    total_weight = sum(weight for weight, _, _ in values)
    return sum(weight * price_pct for weight, price_pct, _ in values) / total_weight


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
