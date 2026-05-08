"""Live eBay Marketplace Insights API client implementing the EbayClient protocol."""
from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx

from zeal.ingestion.ebay_errors import (
    EbayAuthError,
    EbayClientError,
    EbayNetworkError,
    EbayRateLimitError,
    EbayServerError,
)
from zeal.ingestion.ebay_oauth import EbayTokenManager
from zeal.models.ebay import EbaySoldListing

_BASE_URLS: dict[str, str] = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}
_SEARCH_PATH = "/buy/marketplace_insights/v1_beta/item_sales/search"
_MARKETPLACE_ID = "EBAY_US"
_LOOKBACK_DAYS = 90
_REGEX_SEPARATOR = re.compile(r"(?:\\s\+|\\s\*|\\s|/\s*|\s*/|[|]+|[.*+?{}\[\]()\\^$-]+)")
_QUERY_SPACE = re.compile(r"\s+")
_FACE_VALUE_RE = re.compile(r'\$(\d{1,5}(?:\.\d{1,2})?)\b')


def extract_face_value(title: str) -> float:
    """Heuristic: return the largest dollar amount found in the listing title.

    Matches patterns like '$100', '$25.50'. Returns 0.0 when no dollar amount
    is found; the listing filter excludes face_value <= 0 downstream.

    Note: this is a best-effort heuristic. The Marketplace Insights API does
    not return face value directly. v2 may parse item specifics if eBay
    exposes them in a future API version.
    """
    matches = _FACE_VALUE_RE.findall(title)
    if not matches:
        return 0.0
    return max(float(m) for m in matches)


def _query_from_regex(inclusion_regex: str) -> str:
    """Convert a per-merchant inclusion regex to a plain-text eBay search query.

    Regex separators become spaces so grouped and multi-word merchants do not
    collapse into one keyword, e.g. ``home.*depot`` -> ``home depot``.
    """
    plain = _REGEX_SEPARATOR.sub(" ", inclusion_regex)
    plain = _QUERY_SPACE.sub(" ", plain).strip()
    return f"{plain} gift card"


def _parse_item(item: dict[str, Any]) -> EbaySoldListing:
    title = str(item.get("title", ""))
    # Marketplace Insights ItemSales documents lastSoldPrice and itemWebUrl,
    # but not a shipping-cost field. Do not infer Browse-style shippingOptions
    # into this sold-listing price unless eBay documents it for ItemSales.
    sale_price = float(item["lastSoldPrice"]["value"])
    return EbaySoldListing(
        listing_id=str(item["itemId"]),
        title=title,
        sale_price=sale_price,
        sold_at=str(item["lastSoldDate"]),
        face_value=extract_face_value(title),
        source_url=_safe_url(item.get("itemWebUrl") or item.get("itemAffiliateWebUrl")),
        raw_payload=json.dumps(item, sort_keys=True),
    )


def _safe_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


class EbayMarketplaceInsightsClient:
    """Live eBay Marketplace Insights API client.

    Implements the EbayClient protocol. Not constructed until API credentials
    are available; SyntheticEbayClient is used in all earlier phases.
    """

    def __init__(
        self,
        *,
        token_manager: EbayTokenManager,
        environment: Literal["production", "sandbox"],
        http_client: httpx.AsyncClient,
        per_call_sleep_ms: int = 100,
        max_results_default: int = 50,
    ) -> None:
        self._token_manager = token_manager
        self._base_url = _BASE_URLS[environment]
        self._http = http_client
        self._per_call_sleep_s = per_call_sleep_ms / 1000.0
        self._max_results = max_results_default

    async def sold_listings_for_merchant(
        self,
        *,
        merchant_id: str,
        inclusion_regex: str,
        exclusion_regex: str | None,
    ) -> Sequence[EbaySoldListing]:
        _ = (merchant_id, exclusion_regex)  # used downstream in filter_listings
        query = _query_from_regex(inclusion_regex)
        return await self._fetch_all(query)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_all(self, query: str) -> list[EbaySoldListing]:
        cutoff = (datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        first_url = (
            f"{self._base_url}{_SEARCH_PATH}"
            f"?q={urllib.parse.quote(query, safe='')}"
            f"&limit={self._max_results}"
            f"&filter={urllib.parse.quote(f'lastSoldDate:[{cutoff}..]', safe='')}"
        )

        token = await self._token_manager.get_access_token()
        results: list[EbaySoldListing] = []
        current_url: str | None = first_url
        first_page = True

        while current_url and len(results) < self._max_results:
            if not first_page:
                await asyncio.sleep(self._per_call_sleep_s)
            first_page = False

            data, token = await self._get_with_retry(current_url, token)

            for item in data.get("itemSales", []):
                if len(results) >= self._max_results:
                    break
                results.append(_parse_item(item))

            current_url = data.get("next") or None

        return results

    async def _get_with_retry(
        self,
        url: str,
        token: str,
    ) -> tuple[dict[str, Any], str]:
        """Make a GET request with retry logic for 401, 429, 5xx, and network errors.

        Returns (parsed_json, current_token) — token may change on 401 refresh.
        """
        current_token = token
        auth_retried = False
        rate_limit_attempts = 0
        server_retried = False
        network_retried = False

        while True:
            try:
                response = await self._http.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {current_token}",
                        "X-EBAY-C-MARKETPLACE-ID": _MARKETPLACE_ID,
                    },
                )
            except httpx.RequestError as exc:
                if network_retried:
                    raise EbayNetworkError(str(exc)) from exc
                network_retried = True
                await asyncio.sleep(1.0)
                continue

            status = response.status_code

            if status == 200:
                return response.json(), current_token

            if status == 401:
                if auth_retried:
                    raise EbayAuthError("Still 401 after token refresh")
                auth_retried = True
                current_token = await self._token_manager.force_refresh()
                continue

            if status == 429:
                if rate_limit_attempts >= 3:
                    raise EbayRateLimitError("Rate limit exhausted after 3 retries")
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else float(2**rate_limit_attempts)
                rate_limit_attempts += 1
                await asyncio.sleep(wait)
                continue

            if status >= 500:
                if server_retried:
                    raise EbayServerError(f"Server error {status} after retry")
                server_retried = True
                await asyncio.sleep(2.0)
                continue

            raise EbayClientError(f"Unexpected status {status}")
