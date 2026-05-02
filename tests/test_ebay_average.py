import pytest

from zeal.models.ebay import EbayObservation
from zeal.pricing.ebay_average import compute_ebay_average

_ABS = 1e-9


def _obs(listing_id: str, sold_at: str, face_value: float, sale_price: float) -> EbayObservation:
    return EbayObservation(
        merchant_id="test",
        listing_id=listing_id,
        sold_at=sold_at,
        face_value=face_value,
        sale_price=sale_price,
        title="Test",
    )


def test_empty_list_returns_none() -> None:
    assert compute_ebay_average([]) is None


def test_single_observation_returns_exact_ratio() -> None:
    obs = _obs("1", "2026-01-01", face_value=100.0, sale_price=92.0)
    result = compute_ebay_average([obs])
    assert result == pytest.approx(0.92, abs=_ABS)


def test_same_face_value_is_equivalent_to_simple_average() -> None:
    # All $100 cards — weighting has no effect, result equals mean of pcts.
    observations = [
        _obs("1", "2026-01-01", 100.0, 90.0),
        _obs("2", "2026-01-02", 100.0, 80.0),
        _obs("3", "2026-01-03", 100.0, 70.0),
    ]
    result = compute_ebay_average(observations)
    assert result == pytest.approx(0.80, abs=_ABS)


def test_mixed_face_values_are_volume_weighted() -> None:
    # $500 at 90% + $25 at 100%: weighted avg ≠ simple avg (0.95).
    # Correct: (450 + 25) / (500 + 25) = 475 / 525 ≈ 0.90476
    observations = [
        _obs("1", "2026-01-01", 500.0, 450.0),
        _obs("2", "2026-01-02", 25.0, 25.0),
    ]
    result = compute_ebay_average(observations)
    assert result == pytest.approx(475.0 / 525.0, abs=_ABS)


def test_more_than_ten_observations_uses_ten_most_recent() -> None:
    # 10 recent observations (2026-01-03 to 2026-01-12) each at 90%.
    # 2 older observations (2026-01-01, 2026-01-02) at 50% — must be excluded.
    # If only the 10 most recent are used: result = 0.90.
    # If all 12 are used: (10*90 + 2*50) / (12*100) = 1000/1200 ≈ 0.833.
    recent = [
        _obs(f"r{i}", f"2026-01-{i + 3:02d}", 100.0, 90.0) for i in range(10)
    ]
    old = [
        _obs("o1", "2026-01-01", 100.0, 50.0),
        _obs("o2", "2026-01-02", 100.0, 50.0),
    ]
    result = compute_ebay_average(recent + old)
    assert result == pytest.approx(0.90, abs=_ABS)
