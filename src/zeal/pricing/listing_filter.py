from typing import Literal, NamedTuple

type ListingValidityStatus = Literal["valid", "excluded", "suspicious"]

_PARTIAL_KEYWORDS = ("partial", "not full balance")
_SUSPICIOUS_KEYWORDS = (
    "coupon",
    "coupons",
    "bundle",
    "lot",
    "lots",
    "collectible",
    "collectibles",
    "empty",
    "zero balance",
)


class ListingFilterResult(NamedTuple):
    validity_status: ListingValidityStatus
    exclusion_reason: str | None


def classify_listing_candidate(
    *,
    title: str,
    face_value: float,
    sale_price: float,
) -> ListingFilterResult:
    if face_value <= 0.0:
        return ListingFilterResult("excluded", "non_positive_face_value")
    if sale_price <= 0.0:
        return ListingFilterResult("excluded", "non_positive_sale_price")

    normalized = title.casefold()
    if any(keyword in normalized for keyword in _PARTIAL_KEYWORDS):
        return ListingFilterResult("excluded", "partial_balance_suspected")
    if any(keyword in normalized for keyword in _SUSPICIOUS_KEYWORDS):
        return ListingFilterResult("excluded", "suspicious_keyword")

    sell_pct = sale_price / face_value
    if sell_pct < 0.30:
        return ListingFilterResult("excluded", "sell_pct_below_range")
    if sell_pct > 1.10:
        return ListingFilterResult("excluded", "sell_pct_above_range")

    return ListingFilterResult("valid", None)
