import pytest

from zeal.pricing.confidence import score_confidence

# Parametrize over (sample_size, age_days, expected_confidence).
# Covers every cell of the spec §6.4 table plus defensive edge cases.
_CASES = [
    # ── sample_size == 0: age is irrelevant ──────────────────────────────────
    (0, None, "none"),
    (0, 0, "none"),
    (0, 30, "none"),
    (0, 91, "none"),
    # ── sample_size ≥ 10 ─────────────────────────────────────────────────────
    (10, 0, "high"),
    (10, 30, "high"),   # boundary: ≤30 → high
    (10, 31, "medium"),  # boundary: 31 → medium
    (10, 90, "medium"),  # boundary: ≤90 → medium
    # age > 90 should not occur in practice (validity filter blocks it); "none" is safe
    (10, 91, "none"),
    # ── sample_size 5–9 ──────────────────────────────────────────────────────
    (5, 0, "medium"),
    (5, 90, "medium"),   # boundary: ≤90 → medium
    (9, 0, "medium"),
    (9, 90, "medium"),
    (5, 91, "none"),     # outside the valid window → none
    # ── sample_size 1–4 ──────────────────────────────────────────────────────
    (1, 0, "low"),
    (1, 90, "low"),      # boundary: ≤90 → low
    (4, 0, "low"),
    (4, 90, "low"),
    (1, 91, "none"),     # outside the valid window → none
    (4, 91, "none"),
]


@pytest.mark.parametrize("sample_size, age_days, expected", _CASES)
def test_score_confidence(
    sample_size: int, age_days: int | None, expected: str
) -> None:
    assert score_confidence(sample_size, age_days) == expected
