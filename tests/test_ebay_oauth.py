"""Tests for EbayTokenManager OAuth token fetching and caching."""
from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from zeal.ingestion.ebay_errors import EbayAuthError, EbayServerError
from zeal.ingestion.ebay_oauth import EbayTokenManager

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_CREDENTIALS = base64.b64encode(b"test_id:test_secret").decode()
_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
_EXPECTED_BODY = f"grant_type=client_credentials&scope={_SCOPE}".encode()


def _make_manager(http: httpx.AsyncClient) -> EbayTokenManager:
    return EbayTokenManager(
        client_id="test_id",
        client_secret="test_secret",
        environment="production",
        http_client=http,
    )


def _token_response(token: str = "tok123", expires_in: int = 7200) -> httpx.Response:
    return httpx.Response(200, json={"access_token": token, "expires_in": expires_in})


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_token_fetch_returns_token_and_sends_correct_request() -> None:
    with respx.mock:
        route = respx.post(_TOKEN_URL).mock(return_value=_token_response())
        async with httpx.AsyncClient() as http:
            manager = _make_manager(http)
            token = await manager.get_access_token()

    assert token == "tok123"
    assert route.call_count == 1
    req = route.calls.last.request
    assert req.headers["Authorization"] == f"Basic {_CREDENTIALS}"
    assert req.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert req.content == _EXPECTED_BODY


@pytest.mark.asyncio
async def test_token_reused_within_expiry() -> None:
    with respx.mock:
        route = respx.post(_TOKEN_URL).mock(return_value=_token_response())
        async with httpx.AsyncClient() as http:
            manager = _make_manager(http)
            t1 = await manager.get_access_token()
            t2 = await manager.get_access_token()

    assert t1 == t2 == "tok123"
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_token_refreshed_after_expiry() -> None:
    with respx.mock:
        route = respx.post(_TOKEN_URL).mock(return_value=_token_response())
        async with httpx.AsyncClient() as http:
            manager = _make_manager(http)
            await manager.get_access_token()
            assert route.call_count == 1

            # Expire the cached token
            manager._expires_at = datetime.now(UTC) - timedelta(seconds=1)

            await manager.get_access_token()
            assert route.call_count == 2


@pytest.mark.asyncio
async def test_force_refresh_always_fetches_new_token() -> None:
    with respx.mock:
        route = respx.post(_TOKEN_URL).mock(return_value=_token_response())
        async with httpx.AsyncClient() as http:
            manager = _make_manager(http)
            await manager.get_access_token()  # fills cache
            await manager.force_refresh()      # must bypass cache

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_4xx_raises_ebay_auth_error_with_description() -> None:
    with respx.mock:
        respx.post(_TOKEN_URL).mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": "invalid_client",
                    "error_description": "Client authentication failed",
                },
            )
        )
        async with httpx.AsyncClient() as http:
            manager = _make_manager(http)
            with pytest.raises(EbayAuthError, match="Client authentication failed"):
                await manager.get_access_token()


@pytest.mark.asyncio
async def test_5xx_raises_ebay_server_error() -> None:
    with respx.mock:
        respx.post(_TOKEN_URL).mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as http:
            manager = _make_manager(http)
            with pytest.raises(EbayServerError):
                await manager.get_access_token()
