"""Tests for EbayMarketplaceInsightsClient — all HTTP via respx, no live calls."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from zeal.ingestion.ebay_errors import (
    EbayAuthError,
    EbayRateLimitError,
    EbayServerError,
)
from zeal.ingestion.ebay_marketplace_insights_client import (
    EbayMarketplaceInsightsClient,
    extract_face_value,
)
from zeal.models.ebay import EbaySoldListing

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_SEARCH_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"


def _item(
    listing_id: str = "id-1",
    title: str = "Target gift card $100",
    price: str = "90.00",
    sold_at: str = "2025-05-01T10:00:00.000Z",
) -> dict[str, Any]:
    return {
        "itemId": listing_id,
        "title": title,
        "lastSoldPrice": {"value": price, "currency": "USD"},
        "lastSoldDate": sold_at,
    }


def _page(items: list[dict[str, Any]], next_url: str | None = None) -> dict[str, Any]:
    resp: dict[str, Any] = {"itemSales": items}
    if next_url:
        resp["next"] = next_url
    return resp


class _FakeTokenManager:
    """Minimal token manager for client tests — avoids real OAuth."""

    def __init__(
        self, *, token: str = "tok", refresh_token: str | None = None
    ) -> None:
        self._token = token
        self._refresh_token = refresh_token or token
        self.force_refresh_calls = 0

    async def get_access_token(self) -> str:
        return self._token

    async def force_refresh(self) -> str:
        self.force_refresh_calls += 1
        self._token = self._refresh_token
        return self._refresh_token


def _make_client(
    http: httpx.AsyncClient,
    *,
    token: str = "tok",
    refresh_token: str | None = None,
    per_call_sleep_ms: int = 0,
    max_results: int = 50,
) -> tuple[EbayMarketplaceInsightsClient, _FakeTokenManager]:
    mgr = _FakeTokenManager(token=token, refresh_token=refresh_token)
    client = EbayMarketplaceInsightsClient(
        token_manager=mgr,
        environment="production",
        http_client=http,
        per_call_sleep_ms=per_call_sleep_ms,
        max_results_default=max_results,
    )
    return client, mgr


async def _fetch(
    client: EbayMarketplaceInsightsClient,
) -> Sequence[EbaySoldListing]:
    return await client.sold_listings_for_merchant(
        merchant_id="target",
        inclusion_regex="target",
        exclusion_regex=None,
    )


# ---------------------------------------------------------------------------
# Successful query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_query_returns_parsed_listings() -> None:
    with respx.mock:
        respx.get(_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json=_page([_item("id-1", "Target gift card $100", "90.00")]),
            )
        )
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            result = await _fetch(client)

    assert len(result) == 1
    listing = result[0]
    assert listing.listing_id == "id-1"
    assert listing.title == "Target gift card $100"
    assert listing.sale_price == 90.0
    assert listing.face_value == 100.0
    assert listing.sold_at == "2025-05-01T10:00:00.000Z"


@pytest.mark.asyncio
async def test_empty_item_sales_returns_empty_list() -> None:
    with respx.mock:
        respx.get(_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_page([]))
        )
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            result = await _fetch(client)

    assert result == []


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_page_pagination_returns_combined_list() -> None:
    next_url = f"{_SEARCH_URL}?offset=50"
    responses = [
        httpx.Response(200, json=_page([_item("id-1")], next_url=next_url)),
        httpx.Response(200, json=_page([_item("id-2")])),
    ]
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        resp = responses[call_n]
        call_n += 1
        return resp

    with patch("asyncio.sleep", new_callable=AsyncMock), respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            result = await _fetch(client)

    assert [r.listing_id for r in result] == ["id-1", "id-2"]


@pytest.mark.asyncio
async def test_max_results_truncation() -> None:
    # 3 items on page 1, next page available — but max_results=2 stops early
    next_url = f"{_SEARCH_URL}?offset=50"
    responses = [
        httpx.Response(
            200,
            json=_page([_item(f"id-{i}") for i in range(3)], next_url=next_url),
        ),
        httpx.Response(200, json=_page([_item("id-extra")])),
    ]
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        resp = responses[call_n]
        call_n += 1
        return resp

    with patch("asyncio.sleep", new_callable=AsyncMock), respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http, max_results=2)
            result = await _fetch(client)

    assert len(result) == 2
    assert call_n == 1  # stopped after first page


# ---------------------------------------------------------------------------
# 429 / rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_429_then_200_retries_once() -> None:
    responses = [
        httpx.Response(429),
        httpx.Response(200, json=_page([_item("id-1")])),
    ]
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        resp = responses[call_n]
        call_n += 1
        return resp

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            result = await _fetch(client)

    assert len(result) == 1
    assert call_n == 2
    mock_sleep.assert_called_once_with(1.0)  # backoff 2^0 = 1s


@pytest.mark.asyncio
async def test_429_honors_retry_after_header() -> None:
    responses = [
        httpx.Response(429, headers={"Retry-After": "5"}),
        httpx.Response(200, json=_page([_item()])),
    ]
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        resp = responses[call_n]
        call_n += 1
        return resp

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            await _fetch(client)

    mock_sleep.assert_called_once_with(5.0)


@pytest.mark.asyncio
async def test_429_exhausted_raises_rate_limit_error() -> None:
    with patch("asyncio.sleep", new_callable=AsyncMock), respx.mock:
        respx.get(_SEARCH_URL).mock(return_value=httpx.Response(429))
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            with pytest.raises(EbayRateLimitError):
                await _fetch(client)


# ---------------------------------------------------------------------------
# 401 / auth refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_triggers_force_refresh_and_retries() -> None:
    responses = [
        httpx.Response(401),
        httpx.Response(200, json=_page([_item("id-ok")])),
    ]
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        resp = responses[call_n]
        call_n += 1
        return resp

    with respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, mgr = _make_client(http, token="old", refresh_token="new")
            result = await _fetch(client)

    assert mgr.force_refresh_calls == 1
    assert len(result) == 1


@pytest.mark.asyncio
async def test_401_still_401_after_refresh_raises_auth_error() -> None:
    with respx.mock:
        respx.get(_SEARCH_URL).mock(return_value=httpx.Response(401))
        async with httpx.AsyncClient() as http:
            client, mgr = _make_client(http)
            with pytest.raises(EbayAuthError):
                await _fetch(client)

    assert mgr.force_refresh_calls == 1


# ---------------------------------------------------------------------------
# 5xx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_500_then_200_retries_once() -> None:
    responses = [
        httpx.Response(500),
        httpx.Response(200, json=_page([_item("id-ok")])),
    ]
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        resp = responses[call_n]
        call_n += 1
        return resp

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            result = await _fetch(client)

    assert len(result) == 1
    mock_sleep.assert_called_once_with(2.0)


@pytest.mark.asyncio
async def test_500_twice_raises_server_error() -> None:
    with patch("asyncio.sleep", new_callable=AsyncMock), respx.mock:
        respx.get(_SEARCH_URL).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            with pytest.raises(EbayServerError):
                await _fetch(client)


# ---------------------------------------------------------------------------
# Network errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_then_success_retries_once() -> None:
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        call_n += 1
        if call_n == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json=_page([_item("id-ok")]))

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http)
            result = await _fetch(client)

    assert len(result) == 1
    mock_sleep.assert_called_once_with(1.0)


# ---------------------------------------------------------------------------
# per_call_sleep_ms between paginated calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_call_sleep_called_between_pages() -> None:
    next_url = f"{_SEARCH_URL}?offset=50"
    responses = [
        httpx.Response(200, json=_page([_item("id-1")], next_url=next_url)),
        httpx.Response(200, json=_page([_item("id-2")])),
    ]
    call_n = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_n
        resp = responses[call_n]
        call_n += 1
        return resp

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, respx.mock:
        respx.get(_SEARCH_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as http:
            client, _ = _make_client(http, per_call_sleep_ms=250)
            await _fetch(client)

    # sleep called exactly once, between page 1 and page 2, with 0.25s
    mock_sleep.assert_called_once_with(0.25)


# ---------------------------------------------------------------------------
# Face value extraction (pure function — no HTTP)
# ---------------------------------------------------------------------------


def test_face_value_single_amount() -> None:
    assert extract_face_value("Home Depot $100 gift card") == 100.0


def test_face_value_no_dollar_sign_returns_zero() -> None:
    assert extract_face_value("Lowe's gift card") == 0.0


def test_face_value_takes_maximum_when_multiple_amounts() -> None:
    assert extract_face_value("Target $25 ($50 face) gift card") == 50.0


def test_face_value_four_digit_amount() -> None:
    assert extract_face_value("Macy's $1000 gift card") == 1000.0
