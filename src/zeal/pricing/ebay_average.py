from __future__ import annotations

from zeal.models.ebay import EbayObservation

_MAX_OBSERVATIONS = 10


def compute_ebay_average(observations: list[EbayObservation]) -> float | None:
    """Volume-weighted average eBay sell % per spec §6.3.

    Returns sum(sale_price) / sum(face_value) over the most recent N observations,
    N ≤ 10, sorted by sold_at descending. Returns None when the list is empty,
    all observations are filtered out, or sum(face_value) == 0.
    """
    if not observations:
        return None

    recent = sorted(observations, key=lambda o: o.sold_at, reverse=True)[:_MAX_OBSERVATIONS]

    total_face = sum(o.face_value for o in recent)
    if total_face == 0:
        return None

    return sum(o.sale_price for o in recent) / total_face
