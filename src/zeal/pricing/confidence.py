from __future__ import annotations

from typing import Literal


def score_confidence(
    sample_size: int,
    most_recent_observation_age_days: int | None,
) -> Literal["high", "medium", "low", "none"]:
    """Map sample size and data freshness to confidence per spec §6.4.

    When sample_size == 0, age is irrelevant; returns "none" regardless.

    The spec's validity filter (§6.2) removes listings older than 90 days before
    they reach this function, so age > 90 should not occur in normal operation.
    If it does, "none" is the safe answer.
    """
    if sample_size == 0:
        return "none"

    age = most_recent_observation_age_days

    if sample_size >= 10:
        if age is not None and age <= 30:
            return "high"
        if age is not None and age <= 90:
            return "medium"
        return "none"

    if sample_size >= 5:  # 5–9
        if age is not None and age <= 90:
            return "medium"
        return "none"

    # 1–4
    if age is not None and age <= 90:
        return "low"
    return "none"
