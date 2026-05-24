from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx

from zeal.ingestion.ebay_errors import EbayAuthError, EbayNetworkError, EbayServerError

_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
_TOKEN_PATH = "/identity/v1/oauth2/token"
_SAFETY_MARGIN = timedelta(seconds=60)

_BASE_URLS: dict[str, str] = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}


class EbayTokenManager:
    """Fetches and caches an OAuth 2.0 application access token from eBay.

    Token is cached per-instance with a 60-second safety margin before
    expiry. No global state; safe to construct per-request context if needed.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        environment: Literal["production", "sandbox"],
        http_client: httpx.AsyncClient,
    ) -> None:
        self._credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        self._environment = environment
        self._token_url = _BASE_URLS[environment] + _TOKEN_PATH
        self._http = http_client
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def get_access_token(self) -> str:
        if (
            self._token is not None
            and self._expires_at is not None
            and datetime.now(UTC) < self._expires_at - _SAFETY_MARGIN
        ):
            return self._token
        return await self._fetch()

    async def force_refresh(self) -> str:
        self._token = None
        self._expires_at = None
        return await self._fetch()

    async def _fetch(self) -> str:
        try:
            response = await self._http.post(
                self._token_url,
                headers={
                    "Authorization": f"Basic {self._credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content=(
                    f"grant_type=client_credentials"
                    f"&scope={_SCOPE}"
                ).encode(),
            )
        except httpx.RequestError as exc:
            raise EbayNetworkError(str(exc)) from exc

        if response.status_code == 200:
            data = response.json()
            self._token = str(data["access_token"])
            self._expires_at = datetime.now(UTC) + timedelta(
                seconds=int(data["expires_in"])
            )
            return self._token

        if response.status_code < 500:
            body = response.json()
            error = str(body.get("error", ""))
            description = str(body.get("error_description", "OAuth request failed"))
            if error == "invalid_scope":
                raise EbayAuthError(_invalid_scope_message(self._environment, description))
            raise EbayAuthError(description)

        raise EbayServerError(f"OAuth server error: {response.status_code}")


def _invalid_scope_message(environment: str, description: str) -> str:
    env_label = "production" if environment == "production" else environment
    return (
        f"{description}. The {env_label} keyset cannot mint the Marketplace "
        f"Insights scope {_SCOPE}. Check the eBay Developer Portal under "
        f"{env_label.title()} -> Client Credential Grant Type scopes and confirm "
        "buy.marketplace.insights is assigned to this keyset. Do not run the "
        "first-five pilot or fall back to Browse API; sold-listing validation "
        "requires Marketplace Insights entitlement."
    )
