from zeal.pricing.listing_filter import classify_listing_candidate


def test_suspicious_keyword_is_excluded() -> None:
    result = classify_listing_candidate(
        title="Target gift card bundle",
        face_value=100.0,
        sale_price=90.0,
    )
    assert result.validity_status == "excluded"
    assert result.exclusion_reason == "suspicious_keyword"


def test_partial_keyword_gets_partial_reason() -> None:
    result = classify_listing_candidate(
        title="Target gift card partial balance",
        face_value=100.0,
        sale_price=90.0,
    )
    assert result.validity_status == "excluded"
    assert result.exclusion_reason == "partial_balance_suspected"


def test_sell_percentage_below_range_is_excluded() -> None:
    result = classify_listing_candidate(
        title="Target gift card",
        face_value=100.0,
        sale_price=29.0,
    )
    assert result.validity_status == "excluded"
    assert result.exclusion_reason == "sell_pct_below_range"


def test_sell_percentage_above_range_is_excluded() -> None:
    result = classify_listing_candidate(
        title="Target gift card",
        face_value=100.0,
        sale_price=111.0,
    )
    assert result.validity_status == "excluded"
    assert result.exclusion_reason == "sell_pct_above_range"


def test_normal_listing_is_valid() -> None:
    result = classify_listing_candidate(
        title="Target gift card",
        face_value=100.0,
        sale_price=90.0,
    )
    assert result.validity_status == "valid"
    assert result.exclusion_reason is None
