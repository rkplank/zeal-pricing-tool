from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from zeal.ingestion.competitor.errors import CompetitorClientError
from zeal.models.competitor import CompetitorConfidence, CompetitorObservation

logger = logging.getLogger(__name__)

_BUY_PAGE_URL = "https://www.cardcash.com/buy-gift-cards/discount-home-depot-cards"
_SESSION_URL = "https://production-api.cardcash.com/v3/session"
_CARTS_URL = "https://production-api.cardcash.com/v3/carts"
_CARDS_URL_TMPL = "https://production-api.cardcash.com/v3/carts/{cart_id}/cards"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_CC_APP_HEADER = "q3vsT1zXO"
_SESSION_COOKIE = "q3vsT1zXO"
_SESSION_MAX_AGE_S: int = 18 * 60  # re-bootstrap before 20-min JWT expiry
_BUDGET_CAP_S: int = 40 * 60  # 40-min total run cap; caller sets run status='partial'

# Canary anchor ids (Home Depot=27, Starbucks=54) used for catalog integrity checks (§9).
_CANARY_IDS: tuple[int, ...] = (27, 54)
_SCRIPT_TAG = '<script id="injected-variables">'
_INIT_STATE = "window.INITIAL_STATE"

_V3_HEADERS: dict[str, str] = {
    "User-Agent": _USER_AGENT,
    "x-cc-app": _CC_APP_HEADER,
}


class CardCashClient:
    """CardCash competitor scraper — buy-blob (§4.7) and sell-cart (§4.8) surfaces.

    The injected http_client must be an httpx.AsyncClient with cookies enabled (default).
    Never construct AsyncClient internally; never set verify=False.
    """

    def __init__(
        self, http_client: httpx.AsyncClient, *, per_request_sleep_s: float = 0.75
    ) -> None:
        self._http = http_client
        self._per_request_sleep_s = per_request_sleep_s
        self._run_started_at: datetime | None = None
        self._session_acquired_at: datetime | None = None
        self._cart_id: str | None = None
        self._catalog: dict[int, Any] | None = None

    @property
    def source_name(self) -> str:
        return "cardcash"

    # ------------------------------------------------------------------
    # Session / cart lifecycle (§4.6, §4.5)
    # ------------------------------------------------------------------

    async def _ensure_session(self) -> None:
        """Bootstrap or refresh the anonymous session cookie (§4.6).

        Raises CompetitorClientError on failure or if the 40-min budget cap is exceeded.
        """
        now = datetime.now(UTC)
        if self._run_started_at is None:
            self._run_started_at = now
        elif (now - self._run_started_at).total_seconds() >= _BUDGET_CAP_S:
            raise CompetitorClientError(
                "CardCash competitor refresh: 40-minute budget cap exceeded; run is partial"
            )

        needs_bootstrap = (
            self._session_acquired_at is None
            or (now - self._session_acquired_at).total_seconds() >= _SESSION_MAX_AGE_S
        )
        if not needs_bootstrap:
            return

        resp = await self._http.post(_SESSION_URL, json={}, headers=_V3_HEADERS)
        if resp.status_code != 200:
            raise CompetitorClientError(
                f"CardCash session bootstrap failed: HTTP {resp.status_code}"
            )
        if _SESSION_COOKIE not in self._http.cookies:
            raise CompetitorClientError(
                f"CardCash session bootstrap: {_SESSION_COOKIE!r} cookie not set after "
                "POST /v3/session"
            )
        self._session_acquired_at = datetime.now(UTC)
        self._cart_id = None  # invalidate cart when session is refreshed

    async def _ensure_cart(self) -> str:
        """Create a sell cart if one does not exist; return the cartId.

        Raises CompetitorClientError on failure (catastrophic — aborts the run).
        """
        if self._cart_id is not None:
            return self._cart_id
        resp = await self._http.post(_CARTS_URL, json={"action": "sell"}, headers=_V3_HEADERS)
        if resp.status_code != 201:
            raise CompetitorClientError(f"CardCash cart create failed: HTTP {resp.status_code}")
        self._cart_id = resp.json()["cartId"]
        return self._cart_id

    async def _ensure_catalog(self) -> dict[int, Any]:
        """Fetch and cache the buy-blob catalog. Raises CompetitorClientError on failure."""
        if self._catalog is None:
            self._catalog = await self.fetch_buy_catalog()
        return self._catalog

    # ------------------------------------------------------------------
    # Buy-channel helpers (§4.8)
    # ------------------------------------------------------------------

    @staticmethod
    def _buy_channel(entry: dict[str, Any]) -> str:
        """Map cardType blob field to a Zeal channel (§4.8 step 3)."""
        return "buy_mail" if entry.get("cardType") == "physical" else "buy_electronic"

    def _no_data_buy_obs(
        self,
        channel: str,
        *,
        merchant_id: str,
        observed_at: datetime,
    ) -> CompetitorObservation:
        return CompetitorObservation(
            merchant_id=merchant_id,
            source_name="cardcash",
            channel=channel,
            price_pct=None,
            availability="no_data",
            confidence="none",
            observed_at=observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_url=None,
            raw_payload=None,
        )

    async def _post_card_with_retry(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
    ) -> httpx.Response | None:
        """POST card-add with retry/backoff for 429/5xx/network errors (§9).

        Sleeps per_request_sleep_s after the attempt regardless of outcome.
        Returns the response (any status), or None after exhausted network errors.
        """
        backoff = [2.0, 4.0, 8.0]
        result: httpx.Response | None = None

        for attempt in range(3):
            try:
                resp = await self._http.post(url, json=json_body, headers=_V3_HEADERS)
            except httpx.RequestError as exc:
                logger.warning(
                    "CardCash: network error on card-add (attempt %d): %s", attempt + 1, exc
                )
                if attempt < 1:
                    await asyncio.sleep(1.0)
                    continue
                result = None
                break

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after else backoff[min(attempt, len(backoff) - 1)]
                )
                if attempt < 2:
                    await asyncio.sleep(delay)
                    continue
                logger.warning("CardCash: rate-limited after 3 attempts on card-add")
                result = resp
                break

            if resp.status_code >= 500:
                if attempt < 1:
                    await asyncio.sleep(2.0)
                    continue
                logger.warning(
                    "CardCash: server error %s after retry on card-add", resp.status_code
                )
                result = resp
                break

            result = resp
            break

        if self._per_request_sleep_s:
            await asyncio.sleep(self._per_request_sleep_s)
        return result

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def fetch_observations(
        self,
        *,
        merchant_id: str,
        source_key: int,
        observed_at: datetime,
    ) -> list[CompetitorObservation]:
        """Emit up to two observations per merchant: sell-channel (buy blob) + buy-channel (cart).

        Never raises on per-merchant failure; raises CompetitorClientError only on
        structural failures (canary, bootstrap, cart create) that abort the run.
        """
        await self._ensure_session()
        catalog = await self._ensure_catalog()

        entry = catalog.get(source_key)
        if entry is None:
            return [
                self.no_data_sell_observation(
                    merchant_id=merchant_id,
                    source_key=source_key,
                    observed_at=observed_at,
                ),
                self._no_data_buy_obs(
                    "buy_electronic", merchant_id=merchant_id, observed_at=observed_at
                ),
            ]

        sell_obs = self.sell_observation(
            entry, merchant_id=merchant_id, source_key=source_key, observed_at=observed_at
        )
        channel = self._buy_channel(entry)

        # sellIsOff is int (0/1); truthy means CardCash not accepting this merchant.
        if entry["sellIsOff"]:
            return [
                sell_obs,
                self._no_data_buy_obs(channel, merchant_id=merchant_id, observed_at=observed_at),
            ]

        # enterValue clamp to [minFaceValue, maxFaceValue] (§4.5 step 3).
        min_fv: float = entry.get("minFaceValue") or 0.0
        max_fv: float = entry.get("maxFaceValue") or 0.0
        if min_fv > max_fv:
            logger.warning(
                "CardCash: malformed face-value bounds for source_key=%s "
                "(min=%.2f > max=%.2f); skipping cart POST",
                source_key,
                min_fv,
                max_fv,
            )
            return [
                sell_obs,
                self._no_data_buy_obs(channel, merchant_id=merchant_id, observed_at=observed_at),
            ]
        enter_value = int(min(max_fv, max(min_fv, 100)))

        cart_id = await self._ensure_cart()
        url = _CARDS_URL_TMPL.format(cart_id=cart_id)
        payload: dict[str, Any] = {"card": {"merchantId": source_key, "enterValue": enter_value}}

        resp = await self._post_card_with_retry(url, json_body=payload)
        if resp is None:
            return [
                sell_obs,
                self._no_data_buy_obs(channel, merchant_id=merchant_id, observed_at=observed_at),
            ]

        if resp.status_code in (401, 403):
            logger.warning(
                "CardCash: HTTP %s on card-add for source_key=%s; re-bootstrapping session",
                resp.status_code,
                source_key,
            )
            self._session_acquired_at = None
            self._cart_id = None
            await self._ensure_session()
            return [
                sell_obs,
                self._no_data_buy_obs(channel, merchant_id=merchant_id, observed_at=observed_at),
            ]

        if resp.status_code != 201:
            logger.warning(
                "CardCash: card-add returned HTTP %s for source_key=%s",
                resp.status_code,
                source_key,
            )
            return [
                sell_obs,
                self._no_data_buy_obs(channel, merchant_id=merchant_id, observed_at=observed_at),
            ]

        # Match card by merchant == source_key; NEVER use positional index (§4.5 step 3).
        cards: list[Any] = resp.json().get("cards", [])
        matched = next((c for c in cards if c.get("merchant") == source_key), None)
        if matched is None or "percentage" not in matched:
            logger.warning(
                "CardCash: card with merchant==%s not found in cart response for source_key=%s",
                source_key,
                source_key,
            )
            return [
                sell_obs,
                self._no_data_buy_obs(channel, merchant_id=merchant_id, observed_at=observed_at),
            ]

        price_pct = float(matched["percentage"]) / 100.0
        confidence: CompetitorConfidence = "high" if 0.20 <= price_pct <= 1.20 else "low"
        if confidence == "low":
            logger.warning(
                "CardCash: price_pct=%.4f outside [0.20, 1.20] for source_key=%s; confidence=low",
                price_pct,
                source_key,
            )

        buy_obs = CompetitorObservation(
            merchant_id=merchant_id,
            source_name="cardcash",
            channel=channel,
            price_pct=price_pct,
            availability="available",
            confidence=confidence,
            observed_at=observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_url=None,
            raw_payload=json.dumps(matched),
        )
        return [sell_obs, buy_obs]

    # ------------------------------------------------------------------
    # 2a static methods — unchanged
    # ------------------------------------------------------------------

    @staticmethod
    def parse_catalog(html: str) -> dict[int, Any]:
        """Parse the INITIAL_STATE buy catalog from raw buy-page HTML.

        Returns a mapping of CardCash numeric merchant id to full blob entry dict.
        Raises CompetitorClientError on missing script block, JSON failure, or
        canary invariant violation (§9).
        """
        if _SCRIPT_TAG not in html:
            raise CompetitorClientError(
                "CardCash INITIAL_STATE script tag absent — page structure may have changed"
            )
        if _INIT_STATE not in html:
            raise CompetitorClientError(
                "window.INITIAL_STATE assignment absent — page structure may have changed"
            )

        # raw_decode parses exactly one JSON value starting at the first '{' after the
        # INITIAL_STATE prefix, so trailing variable assignments (e.g.; maxmind_user_id=...)
        # do not cause mis-termination the way a greedy regex would.
        try:
            start = html.index("{", html.index(_INIT_STATE))
            raw: Any
            raw, _ = json.JSONDecoder().raw_decode(html, start)
        except (ValueError, KeyError) as exc:
            raise CompetitorClientError(f"Failed to parse INITIAL_STATE JSON: {exc}") from exc

        try:
            entries: list[Any] = raw["merchantsBuy"]["sortedByName"]
        except (KeyError, TypeError) as exc:
            raise CompetitorClientError(
                f"Unexpected INITIAL_STATE structure (merchantsBuy.sortedByName missing): {exc}"
            ) from exc

        # Canary: catalog must have >100 entries (§9).
        if len(entries) <= 100:
            raise CompetitorClientError(
                f"Catalog has only {len(entries)} entries — expected >100; "
                "likely a truncated or broken response"
            )

        by_id: dict[int, Any] = {e["id"]: e for e in entries}

        # Canary: at least one anchor merchant present with valid id type and upToPercentage.
        anchor: Any = next((by_id[cid] for cid in _CANARY_IDS if cid in by_id), None)
        if anchor is None:
            raise CompetitorClientError(
                f"No canary anchor merchant found (expected ids {_CANARY_IDS})"
            )
        if not isinstance(anchor["id"], int):
            raise CompetitorClientError(
                f"Canary anchor id field is not int: {type(anchor['id']).__name__!r}"
            )
        anchor_pct: Any = anchor["upToPercentage"]
        if not isinstance(anchor_pct, (int, float)) or not (0 <= anchor_pct <= 100):
            raise CompetitorClientError(
                f"Canary anchor upToPercentage={anchor_pct!r} is out of range [0, 100]"
            )

        return by_id

    @staticmethod
    def sell_observation(
        entry: dict[str, Any],
        *,
        merchant_id: str,
        source_key: int,
        observed_at: datetime,
    ) -> CompetitorObservation:
        """Build a sell-channel observation from a catalog entry (§4.7 steps 7–11, §6).

        sellIsOff and cardsAvailable are int (not bool) in the live CardCash API response.
        """
        observed_str = observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        slug: str = str(entry.get("slug") or "")
        source_url: str | None = (
            f"https://www.cardcash.com/buy-gift-cards/{slug}" if slug else _BUY_PAGE_URL
        )
        raw_payload = json.dumps(entry)

        # Availability (§4.7 step 7).
        if entry["sellIsOff"] or not entry["cardsAvailable"]:
            return CompetitorObservation(
                merchant_id=merchant_id,
                source_name="cardcash",
                channel="sell",
                price_pct=None,
                availability="unavailable",
                confidence="medium",
                observed_at=observed_str,
                source_url=source_url,
                raw_payload=raw_payload,
            )

        # Price computation (§4.7 step 8) and confidence assignment (§6).
        up_to: Any = entry["upToPercentage"]
        price_pct: float | None
        confidence: CompetitorConfidence

        if isinstance(up_to, (int, float)):
            price_pct = 1.0 - float(up_to) / 100.0
        else:
            price_pct = None

        pct_ok = isinstance(up_to, (int, float)) and 0 <= up_to <= 100
        band_ok = price_pct is not None and 0.20 <= price_pct <= 1.20

        if not pct_ok:
            logger.warning(
                "CardCash upToPercentage=%r out of [0,100] for source_key=%s; confidence=low",
                up_to,
                source_key,
            )
            confidence = "low"
        elif not band_ok:
            logger.warning(
                "Derived price_pct=%r out of [0.20,1.20] for source_key=%s; confidence=low",
                price_pct,
                source_key,
            )
            confidence = "low"
        else:
            confidence = "medium"

        return CompetitorObservation(
            merchant_id=merchant_id,
            source_name="cardcash",
            channel="sell",
            price_pct=price_pct,
            availability="available",
            confidence=confidence,
            observed_at=observed_str,
            source_url=source_url,
            raw_payload=raw_payload,
        )

    @staticmethod
    def no_data_sell_observation(
        *,
        merchant_id: str,
        source_key: int,
        observed_at: datetime,
    ) -> CompetitorObservation:
        """Observation for a Zeal merchant absent from the CardCash catalog (§4.7 step 10)."""
        return CompetitorObservation(
            merchant_id=merchant_id,
            source_name="cardcash",
            channel="sell",
            price_pct=None,
            availability="no_data",
            confidence="none",
            observed_at=observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_url=None,
            raw_payload=None,
        )

    async def fetch_buy_catalog(self, url: str | None = None) -> dict[int, Any]:
        """GET a buy page and return the parsed catalog dict.

        Raises CompetitorClientError on HTTP errors or catalog parse failures.
        """
        target = url or _BUY_PAGE_URL
        resp = await self._http.get(target, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        return self.parse_catalog(resp.text)
