from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from zeal.ingestion.competitor.errors import CompetitorClientError
from zeal.models.competitor import CompetitorConfidence, CompetitorObservation

logger = logging.getLogger(__name__)

_BUY_PAGE_URL = "https://www.cardcash.com/buy-gift-cards/discount-home-depot-cards"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
# Canary anchor ids (Home Depot=27, Starbucks=54) used for catalog integrity checks (§9).
_CANARY_IDS: tuple[int, ...] = (27, 54)
_SCRIPT_TAG = '<script id="injected-variables">'
_INIT_STATE = "window.INITIAL_STATE"


class CardCashClient:
    """CardCash competitor scraper — buy-blob surface only (Prompt 2a).

    Prompt 2b adds: session bootstrap (§4.6), sell-cart flow (§4.5/§4.8), and
    full fetch_observations() composition.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    @property
    def source_name(self) -> str:
        return "cardcash"

    async def fetch_observations(
        self,
        *,
        merchant_id: str,
        source_key: int,
        observed_at: datetime,
    ) -> list[CompetitorObservation]:
        # Sell flow (§4.5–§4.8) and full composition deferred to Prompt 2b.
        raise NotImplementedError("sell flow + compose: Prompt 2b")

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
            raise CompetitorClientError(
                f"Failed to parse INITIAL_STATE JSON: {exc}"
            ) from exc

        try:
            entries: list[Any] = raw["merchantsBuy"]["sortedByName"]
        except (KeyError, TypeError) as exc:
            raise CompetitorClientError(
                "Unexpected INITIAL_STATE structure (merchantsBuy.sortedByName missing): "
                f"{exc}"
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
        Session bootstrap (§4.6) is the caller's responsibility and is deferred to Prompt 2b.
        """
        target = url or _BUY_PAGE_URL
        resp = await self._http.get(target, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        return self.parse_catalog(resp.text)
