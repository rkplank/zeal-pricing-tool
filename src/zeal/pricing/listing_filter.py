import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from zeal.models.ebay import EbaySoldListing
from zeal.models.merchant import MerchantRecord

_LOOKBACK_DAYS = 90
_SELL_PCT_MIN = 0.30
_SELL_PCT_MAX = 1.10

_PARTIAL_KEYWORDS = ("partial", "not full balance")
_SUSPICIOUS_RE = re.compile(
    r"\b(?:coupon|coupons|bundle|lot|lots|collectible|collectibles|empty|zero balance)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExcludedListing:
    listing: EbaySoldListing
    exclusion_reason: str


@dataclass(frozen=True)
class ListingFilterResult:
    valid: list[EbaySoldListing]
    excluded: list[ExcludedListing]


def filter_listings(
    listings: Sequence[EbaySoldListing],
    merchant: MerchantRecord,
    *,
    now: datetime | None = None,
) -> ListingFilterResult:
    cutoff = _as_naive_utc(now if now is not None else datetime.now(UTC)) - timedelta(
        days=_LOOKBACK_DAYS
    )
    inclusion_re = re.compile(merchant.inclusion_regex, re.IGNORECASE)
    exclusion_re = (
        re.compile(merchant.exclusion_regex, re.IGNORECASE) if merchant.exclusion_regex else None
    )

    valid: list[EbaySoldListing] = []
    excluded: list[ExcludedListing] = []
    for listing in listings:
        reason = _classify(listing, cutoff, inclusion_re, exclusion_re)
        if reason is None:
            valid.append(listing)
        else:
            excluded.append(ExcludedListing(listing=listing, exclusion_reason=reason))
    return ListingFilterResult(valid=valid, excluded=excluded)


def _as_naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _classify(
    listing: EbaySoldListing,
    cutoff: datetime,
    inclusion_re: re.Pattern[str],
    exclusion_re: re.Pattern[str] | None,
) -> str | None:
    sold_at = _as_naive_utc(datetime.fromisoformat(listing.sold_at))
    if sold_at < cutoff:
        return "sale_date_too_old"
    if listing.face_value <= 0:
        return "zero_or_negative_face_value"
    if listing.sale_price <= 0:
        return "zero_or_negative_price"
    if not inclusion_re.search(listing.title):
        return "merchant_inclusion_regex_miss"
    if exclusion_re is not None and exclusion_re.search(listing.title):
        return "merchant_exclusion_regex_hit"
    title_lower = listing.title.casefold()
    if any(kw in title_lower for kw in _PARTIAL_KEYWORDS):
        return "partial_balance_suspected"
    if _SUSPICIOUS_RE.search(listing.title):
        return "suspicious_keyword"
    sell_pct = listing.sale_price / listing.face_value
    if sell_pct < _SELL_PCT_MIN or sell_pct > _SELL_PCT_MAX:
        return "sell_pct_out_of_range"
    return None
