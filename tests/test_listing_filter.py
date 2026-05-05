from datetime import datetime, timedelta

from zeal.models.ebay import EbaySoldListing
from zeal.models.merchant import MerchantRecord
from zeal.pricing.listing_filter import ListingFilterResult, filter_listings

# Fixed reference time so tests are deterministic.
_NOW = datetime(2025, 6, 1, 12, 0, 0)
_RECENT = (_NOW - timedelta(days=1)).isoformat()


def _merchant(
    inclusion_regex: str = "target",
    exclusion_regex: str | None = None,
) -> MerchantRecord:
    return MerchantRecord(
        merchant_id="target",
        display_name="Target",
        tier="C",
        in_store_margin=0.25,
        in_mail_margin=0.07,
        ebay_differential=0.045,
        in_store_eligible=True,
        in_mail_eligible=True,
        electronic_eligible=True,
        merch_credit_variant=False,
        inclusion_regex=inclusion_regex,
        exclusion_regex=exclusion_regex,
        created_at="2025-01-01T00:00:00",
        updated_at="2025-01-01T00:00:00",
    )


def _listing(
    title: str = "Target gift card",
    face_value: float = 100.0,
    sale_price: float = 85.0,
    sold_at: str = _RECENT,
    listing_id: str = "test-001",
) -> EbaySoldListing:
    return EbaySoldListing(
        listing_id=listing_id,
        sold_at=sold_at,
        face_value=face_value,
        sale_price=sale_price,
        title=title,
    )


def _run(listing: EbaySoldListing, **merchant_kwargs: object) -> ListingFilterResult:
    return filter_listings([listing], _merchant(**merchant_kwargs), now=_NOW)  # type: ignore[arg-type]


# --- one test per exclusion reason ---


def test_sale_date_too_old() -> None:
    old_date = (_NOW - timedelta(days=91)).isoformat()
    result = _run(_listing(sold_at=old_date))
    assert result.excluded[0].exclusion_reason == "sale_date_too_old"
    assert result.valid == []


def test_zero_or_negative_face_value() -> None:
    result = _run(_listing(face_value=0.0))
    assert result.excluded[0].exclusion_reason == "zero_or_negative_face_value"


def test_zero_or_negative_price() -> None:
    result = _run(_listing(sale_price=0.0))
    assert result.excluded[0].exclusion_reason == "zero_or_negative_price"


def test_merchant_inclusion_regex_miss() -> None:
    result = _run(_listing(title="Amazon gift card"))
    assert result.excluded[0].exclusion_reason == "merchant_inclusion_regex_miss"


def test_merchant_exclusion_regex_hit() -> None:
    result = _run(
        _listing(title="Target gift card merchandise credit"),
        exclusion_regex="merchandise credit",
    )
    assert result.excluded[0].exclusion_reason == "merchant_exclusion_regex_hit"


def test_partial_balance_suspected() -> None:
    result = _run(_listing(title="Target gift card partial balance"))
    assert result.excluded[0].exclusion_reason == "partial_balance_suspected"


def test_suspicious_keyword() -> None:
    result = _run(_listing(title="Target gift card bundle"))
    assert result.excluded[0].exclusion_reason == "suspicious_keyword"


def test_sell_pct_out_of_range() -> None:
    result = _run(_listing(sale_price=25.0))  # 25/100 = 0.25 < 0.30
    assert result.excluded[0].exclusion_reason == "sell_pct_out_of_range"


# --- precedence ---


def test_precedence_earlier_rule_wins() -> None:
    # violates rule 7 (suspicious_keyword: "bundle") AND rule 8 (sell_pct_out_of_range: 0.25)
    result = _run(_listing(title="Target gift card bundle", sale_price=25.0))
    assert result.excluded[0].exclusion_reason == "suspicious_keyword"


# --- happy path ---


def test_happy_path_multiple_listings_returned_in_order() -> None:
    listings = [
        _listing(
            sold_at=(_NOW - timedelta(days=i)).isoformat(),
            listing_id=f"id-{i}",
        )
        for i in range(3)
    ]
    result = filter_listings(listings, _merchant(), now=_NOW)
    assert len(result.valid) == 3
    assert len(result.excluded) == 0
    assert [v.listing_id for v in result.valid] == ["id-0", "id-1", "id-2"]


# --- exclusion_regex = None ---


def test_exclusion_regex_none_is_skipped() -> None:
    result = _run(_listing(), exclusion_regex=None)
    assert len(result.valid) == 1
    assert result.excluded == []


# --- now injection boundary ---


def test_now_injection_exactly_90_days_old_is_valid() -> None:
    cutoff = _NOW - timedelta(days=90)
    result = _run(_listing(sold_at=cutoff.isoformat()))
    assert len(result.valid) == 1
    assert result.excluded == []


def test_now_injection_90_days_plus_1_second_is_excluded() -> None:
    just_past = _NOW - timedelta(days=90) - timedelta(seconds=1)
    result = _run(_listing(sold_at=just_past.isoformat()))
    assert result.excluded[0].exclusion_reason == "sale_date_too_old"


# --- word-boundary: "lot" must not match "Lottery" ---


def test_word_boundary_lot_does_not_match_lottery() -> None:
    merchant = _merchant(inclusion_regex="lottery")
    listing = _listing(title="Lottery gift card $100")
    result = filter_listings([listing], merchant, now=_NOW)
    assert len(result.valid) == 1
    assert result.excluded == []
