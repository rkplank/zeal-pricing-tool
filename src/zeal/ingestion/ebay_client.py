from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from zeal.models.ebay import EbaySoldListing


class EbayClient(Protocol):
    """Interface implemented by future live eBay clients and Phase 2 test doubles."""

    async def sold_listings_for_merchant(
        self,
        *,
        merchant_id: str,
        inclusion_regex: str,
        exclusion_regex: str | None,
    ) -> Sequence[EbaySoldListing]:
        """Return recent sold listings for one merchant without applying pricing filters."""


class SyntheticEbayClient:
    """In-memory eBay client for tests and demos; never performs network calls."""

    def __init__(self, listings: dict[str, Iterable[EbaySoldListing]] | None = None) -> None:
        self._listings = {
            merchant_id: tuple(merchant_listings)
            for merchant_id, merchant_listings in (listings or {}).items()
        }

    async def sold_listings_for_merchant(
        self,
        *,
        merchant_id: str,
        inclusion_regex: str,
        exclusion_regex: str | None,
    ) -> Sequence[EbaySoldListing]:
        _ = (inclusion_regex, exclusion_regex)
        return self._listings.get(merchant_id, ())
