"""CardCash scraper tests — buy-blob (2a) and sell-cart (2b) surfaces.

All HTTP is mocked via respx; no live network calls.

Firewall-derived literals (hand-computed from real fixture 2026-06-14):
  Buy-blob:
    Home Depot (id=27):  upToPercentage=2   → price_pct = 1 - 2/100   = 0.98
    Starbucks  (id=54):  upToPercentage=5.6 → price_pct = 1 - 5.6/100 = 0.944
  Sell-cart (card_add_response.json captured 2026-06-21):
    Home Depot (id=27):  percentage=83 → price_pct = 83/100 = 0.83
    Starbucks  (id=54):  percentage=76 → price_pct = 76/100 = 0.76
"""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from zeal.ingestion.competitor.cardcash import CardCashClient
from zeal.ingestion.competitor.errors import CompetitorClientError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIXTURE_DIR = pathlib.Path("tests/fixtures/cardcash")
_BUY_HTML = (_FIXTURE_DIR / "buy_catalog.html").read_text(encoding="utf-8")
_CART_CREATE_BODY = (_FIXTURE_DIR / "cart_create_response.json").read_text(encoding="utf-8")
_CARD_ADD_BODY = (_FIXTURE_DIR / "card_add_response.json").read_text(encoding="utf-8")
_T0 = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)

# Buy-blob firewall literals (hand-computed, never imported from module under test)
_HD_SELL_PRICE_PCT = 0.98  # Home Depot  id=27  upToPercentage=2    1-2/100
_SB_SELL_PRICE_PCT = 0.944  # Starbucks   id=54  upToPercentage=5.6  1-5.6/100

# Sell-cart firewall literals (hand-computed from card_add_response.json)
_HD_BUY_PRICE_PCT = 0.83  # Home Depot  id=27  percentage=83  83/100
_SB_BUY_PRICE_PCT = 0.76  # Starbucks   id=54  percentage=76  76/100

_CART_ID = json.loads(_CART_CREATE_BODY)["cartId"]
_BUY_PAGE_URL = "https://www.cardcash.com/buy-gift-cards/discount-home-depot-cards"
_SESSION_URL = "https://production-api.cardcash.com/v3/session"
_CARTS_URL = "https://production-api.cardcash.com/v3/carts"
_CARDS_URL = f"https://production-api.cardcash.com/v3/carts/{_CART_ID}/cards"

# ---------------------------------------------------------------------------
# Constructed-fixture helpers (for branches not naturally present in the real file)
# ---------------------------------------------------------------------------


def _entry(
    id_: int,
    up_to: float | int = 5.0,
    sell_is_off: int = 0,
    cards_avail: int = 10,
    card_type: str = "ecode",
    min_fv: float = 5.0,
    max_fv: float = 500.0,
) -> dict[str, Any]:
    return {
        "id": id_,
        "slug": f"test-merchant-{id_}",
        "upToPercentage": up_to,
        "sellIsOff": sell_is_off,
        "cardsAvailable": cards_avail,
        "cardType": card_type,
        "minFaceValue": min_fv,
        "maxFaceValue": max_fv,
        "aliases": [],
    }


def _html(entries: list[dict[str, Any]]) -> str:
    blob = {"merchantsBuy": {"sortedByName": entries}}
    return f'<script id="injected-variables">window.INITIAL_STATE = {json.dumps(blob)};</script>'


# 101 generic entries that satisfy the count canary — used in canary tests that need
# a valid-length catalog but want to control specific entries.
_GENERIC_101 = [_entry(1000 + i) for i in range(101)]


def _make_client(
    http: httpx.AsyncClient,
    *,
    per_request_sleep_s: float = 0,
    catalog: dict[int, Any] | None = None,
) -> CardCashClient:
    """Return a CardCashClient with session pre-marked and (optionally) catalog pre-loaded."""
    cc = CardCashClient(http, per_request_sleep_s=per_request_sleep_s)
    cc._session_acquired_at = datetime.now(UTC)
    if catalog is not None:
        cc._catalog = catalog
    return cc


# ---------------------------------------------------------------------------
# parse_catalog — real fixture
# ---------------------------------------------------------------------------


def test_fixture_gate() -> None:
    """Confirm the real fixture parses and contains both anchor merchants."""
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    assert len(catalog) > 100
    assert 27 in catalog, "Home Depot (id=27) missing from fixture"
    assert 54 in catalog, "Starbucks (id=54) missing from fixture"


# ---------------------------------------------------------------------------
# parse_catalog — error cases (constructed snippets)
# ---------------------------------------------------------------------------


def test_parse_catalog_missing_script_tag() -> None:
    bad = _BUY_HTML.replace('<script id="injected-variables">', "<!-- removed -->", 1)
    with pytest.raises(CompetitorClientError, match="script tag absent"):
        CardCashClient.parse_catalog(bad)


def test_parse_catalog_missing_init_state() -> None:
    bad = _BUY_HTML.replace("window.INITIAL_STATE", "window.OTHER_STATE", 1)
    with pytest.raises(CompetitorClientError, match="INITIAL_STATE assignment absent"):
        CardCashClient.parse_catalog(bad)


def test_parse_catalog_malformed_json() -> None:
    html = '<script id="injected-variables">window.INITIAL_STATE = {BROKEN};</script>'
    with pytest.raises(CompetitorClientError, match="Failed to parse"):
        CardCashClient.parse_catalog(html)


def test_canary_too_few_entries() -> None:
    entries = [_entry(27)] * 5  # 5 entries — below the >100 threshold
    with pytest.raises(CompetitorClientError, match="only 5 entries"):
        CardCashClient.parse_catalog(_html(entries))


def test_canary_no_anchor_merchant() -> None:
    # 101 entries, none with id 27 or 54
    with pytest.raises(CompetitorClientError, match="canary anchor merchant"):
        CardCashClient.parse_catalog(_html(_GENERIC_101))


def test_canary_anchor_pct_out_of_range() -> None:
    entries = [_entry(27, up_to=150.0)] + _GENERIC_101
    with pytest.raises(CompetitorClientError, match="out of range"):
        CardCashClient.parse_catalog(_html(entries))


def test_canary_anchor_id_not_int() -> None:
    # id is a float rather than int; 27.0 == 27 in Python so the key lookup still works,
    # but the isinstance(int) canary must fire.
    raw_entry: dict[str, Any] = {**_entry(27), "id": 27.0}
    entries = [raw_entry] + _GENERIC_101
    with pytest.raises(CompetitorClientError, match="id field is not int"):
        CardCashClient.parse_catalog(_html(entries))


# ---------------------------------------------------------------------------
# sell_observation — happy paths (real fixture, firewall literals)
# ---------------------------------------------------------------------------


def test_sell_observation_home_depot() -> None:
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    obs = CardCashClient.sell_observation(
        catalog[27], merchant_id="home-depot", source_key=27, observed_at=_T0
    )
    assert obs.merchant_id == "home-depot"
    assert obs.source_name == "cardcash"
    assert obs.channel == "sell"
    assert obs.availability == "available"
    assert obs.confidence == "medium"
    assert obs.price_pct == pytest.approx(_HD_SELL_PRICE_PCT, abs=1e-9)
    assert obs.raw_payload is not None
    payload = json.loads(obs.raw_payload)
    assert payload["id"] == 27
    assert "cardType" in payload  # retained for channel mapping


def test_sell_observation_starbucks() -> None:
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    obs = CardCashClient.sell_observation(
        catalog[54], merchant_id="starbucks", source_key=54, observed_at=_T0
    )
    assert obs.availability == "available"
    assert obs.confidence == "medium"
    assert obs.price_pct == pytest.approx(_SB_SELL_PRICE_PCT, abs=1e-9)


def test_sell_observation_observed_at_format() -> None:
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    obs = CardCashClient.sell_observation(
        catalog[27], merchant_id="home-depot", source_key=27, observed_at=_T0
    )
    assert obs.observed_at == "2026-06-14T12:00:00Z"


# ---------------------------------------------------------------------------
# sell_observation — unavailability (real fixture entries)
# ---------------------------------------------------------------------------


def test_sell_observation_sell_is_off() -> None:
    # id=126 has sellIsOff=1 in the real fixture.
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    entry = catalog[126]
    assert entry["sellIsOff"], "fixture precondition: id=126 must have sellIsOff truthy"
    obs = CardCashClient.sell_observation(
        entry, merchant_id="merchant-x", source_key=126, observed_at=_T0
    )
    assert obs.availability == "unavailable"
    assert obs.confidence == "medium"
    assert obs.price_pct is None


def test_sell_observation_no_cards_available() -> None:
    # id=257 has cardsAvailable=0 in the real fixture.
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    entry = catalog[257]
    assert not entry["cardsAvailable"], "fixture precondition: id=257 must have cardsAvailable=0"
    obs = CardCashClient.sell_observation(
        entry, merchant_id="merchant-y", source_key=257, observed_at=_T0
    )
    assert obs.availability == "unavailable"
    assert obs.confidence == "medium"
    assert obs.price_pct is None


# ---------------------------------------------------------------------------
# sell_observation — out-of-range / low confidence (constructed entries)
# ---------------------------------------------------------------------------


def test_sell_observation_upto_out_of_range() -> None:
    # upToPercentage=105 → pct_ok=False → confidence="low"; price_pct still derived.
    entry = _entry(9001, up_to=105.0)
    obs = CardCashClient.sell_observation(
        entry, merchant_id="edge", source_key=9001, observed_at=_T0
    )
    assert obs.confidence == "low"
    assert obs.availability == "available"
    assert obs.price_pct == pytest.approx(1 - 105.0 / 100, abs=1e-9)


def test_sell_observation_price_out_of_band() -> None:
    # upToPercentage=85 is in [0,100] but price_pct=0.15 is below the [0.20,1.20] band.
    entry = _entry(9002, up_to=85.0)
    obs = CardCashClient.sell_observation(
        entry, merchant_id="edge", source_key=9002, observed_at=_T0
    )
    assert obs.confidence == "low"
    assert obs.availability == "available"
    assert obs.price_pct == pytest.approx(0.15, abs=1e-9)


def test_sell_observation_upto_zero_is_valid() -> None:
    # upToPercentage=0 → price_pct=1.0; valid and must not be treated as unavailable (§4.7 step 8).
    entry = _entry(9003, up_to=0.0)
    obs = CardCashClient.sell_observation(
        entry, merchant_id="full-face", source_key=9003, observed_at=_T0
    )
    assert obs.availability == "available"
    assert obs.confidence == "medium"
    assert obs.price_pct == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# no_data_sell_observation
# ---------------------------------------------------------------------------


def test_no_data_sell_observation() -> None:
    obs = CardCashClient.no_data_sell_observation(
        merchant_id="unknown-brand", source_key=99999, observed_at=_T0
    )
    assert obs.availability == "no_data"
    assert obs.confidence == "none"
    assert obs.price_pct is None
    assert obs.channel == "sell"
    assert obs.source_name == "cardcash"
    assert obs.raw_payload is None


# ---------------------------------------------------------------------------
# fetch_observations — sell-cart happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_observations_home_depot_ecode() -> None:
    """Home Depot: ecode → buy_electronic, firewall literal 0.83, confidence high."""
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=_CARD_ADD_BODY))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(
                merchant_id="home-depot", source_key=27, observed_at=_T0
            )

    assert len(obs) == 2
    sell_obs = next(o for o in obs if o.channel == "sell")
    buy_obs = next(o for o in obs if o.channel == "buy_electronic")
    assert sell_obs.price_pct == pytest.approx(_HD_SELL_PRICE_PCT, abs=1e-9)
    assert buy_obs.price_pct == pytest.approx(_HD_BUY_PRICE_PCT, abs=1e-9)
    assert buy_obs.confidence == "high"
    assert buy_obs.availability == "available"
    assert buy_obs.source_name == "cardcash"
    assert buy_obs.merchant_id == "home-depot"
    assert buy_obs.observed_at == "2026-06-14T12:00:00Z"


@pytest.mark.asyncio
async def test_fetch_observations_starbucks_ecode() -> None:
    """Starbucks: ecode → buy_electronic, firewall literal 0.76."""
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=_CARD_ADD_BODY))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(
                merchant_id="starbucks", source_key=54, observed_at=_T0
            )

    buy_obs = next(o for o in obs if o.channel == "buy_electronic")
    assert buy_obs.price_pct == pytest.approx(_SB_BUY_PRICE_PCT, abs=1e-9)
    assert buy_obs.confidence == "high"


@pytest.mark.asyncio
async def test_fetch_observations_channel_physical() -> None:
    """cardType=physical → buy_mail channel."""
    catalog = {27: _entry(27, card_type="physical")}
    card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [{"merchant": 27, "percentage": 80, "enterValue": 100}],
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.channel == "buy_mail"


@pytest.mark.asyncio
async def test_fetch_observations_channel_both() -> None:
    """cardType=BOTH → buy_electronic (v1 simplification, §4.8 step 3)."""
    catalog = {27: _entry(27, card_type="BOTH")}
    card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [{"merchant": 27, "percentage": 82, "enterValue": 100}],
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.channel == "buy_electronic"


# ---------------------------------------------------------------------------
# fetch_observations — match by merchant field, not by positional index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_match_by_merchant_not_last() -> None:
    """Match by card["merchant"]==source_key even when target is NOT the last card.

    The cart accumulates cards across POSTs; positional-index lookup would return
    the wrong merchant. Home Depot (27, 83%) is FIRST; Starbucks (54, 76%) is LAST.
    Correct field-match must yield 0.83, not 0.76.
    """
    catalog = {27: _entry(27)}
    multi_card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [
                {"merchant": 27, "percentage": 83, "enterValue": 100},
                {"merchant": 54, "percentage": 76, "enterValue": 100},
            ],
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=multi_card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(
                merchant_id="home-depot", source_key=27, observed_at=_T0
            )

    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.price_pct == pytest.approx(0.83, abs=1e-9), (
        "Got wrong price_pct — positional index lookup would return Starbucks (0.76) "
        "instead of Home Depot (0.83); use merchant-field match"
    )


# ---------------------------------------------------------------------------
# fetch_observations — sellIsOff → no POST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_is_off_no_post() -> None:
    """sellIsOff=1 → skip cart POST entirely; emit no_data buy obs."""
    catalog = {27: _entry(27, sell_is_off=1)}
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        cards_route = respx.post(_CARDS_URL).mock(
            return_value=httpx.Response(201, text=_CARD_ADD_BODY)
        )
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    assert cards_route.call_count == 0, "Card-add POST must NOT be called when sellIsOff=1"
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"
    assert buy_obs.confidence == "none"
    assert buy_obs.price_pct is None


# ---------------------------------------------------------------------------
# fetch_observations — non-201 card-add → no_data, continue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_201_card_add_no_data() -> None:
    """non-201 on card-add → no_data, run continues (does not raise)."""
    catalog = {27: _entry(27)}
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(400, json={"message": "bad"}))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"
    assert buy_obs.confidence == "none"
    assert buy_obs.price_pct is None


# ---------------------------------------------------------------------------
# fetch_observations — missing or unmatched card in 201 response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_percentage_no_data() -> None:
    """201 response with matched card but 'percentage' key absent → no_data."""
    catalog = {27: _entry(27)}
    card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [{"merchant": 27, "enterValue": 100}],  # no "percentage"
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"
    assert buy_obs.confidence == "none"


@pytest.mark.asyncio
async def test_unmatched_merchant_no_data() -> None:
    """201 response with no card matching source_key → no_data."""
    catalog = {27: _entry(27)}
    card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [{"merchant": 999, "percentage": 80, "enterValue": 100}],  # wrong merchant
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"


# ---------------------------------------------------------------------------
# fetch_observations — cart create failure → CompetitorClientError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cart_create_failure_raises() -> None:
    """Non-201 cart create → CompetitorClientError (aborts run)."""
    catalog = {27: _entry(27)}
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(500, json={"error": "oops"}))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            with pytest.raises(CompetitorClientError, match="cart create failed"):
                await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)


# ---------------------------------------------------------------------------
# fetch_observations — enterValue clamp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enter_value_clamp_below_min() -> None:
    """100 < minFaceValue → clamp to minFaceValue (200)."""
    catalog = {27: _entry(27, min_fv=200.0, max_fv=500.0)}
    card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [{"merchant": 27, "percentage": 80, "enterValue": 200}],
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        cards_route = respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    assert cards_route.call_count == 1
    sent_payload = json.loads(cards_route.calls[0].request.content)
    assert sent_payload["card"]["enterValue"] == 200


@pytest.mark.asyncio
async def test_enter_value_clamp_above_max() -> None:
    """100 > maxFaceValue → clamp to maxFaceValue (50)."""
    catalog = {27: _entry(27, min_fv=10.0, max_fv=50.0)}
    card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [{"merchant": 27, "percentage": 80, "enterValue": 50}],
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        cards_route = respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    sent_payload = json.loads(cards_route.calls[0].request.content)
    assert sent_payload["card"]["enterValue"] == 50


@pytest.mark.asyncio
async def test_enter_value_malformed_bounds_no_post() -> None:
    """minFaceValue > maxFaceValue → no_data, no cart POST."""
    catalog = {27: _entry(27, min_fv=500.0, max_fv=10.0)}  # malformed: min > max
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        cards_route = respx.post(_CARDS_URL).mock(
            return_value=httpx.Response(201, text=_CARD_ADD_BODY)
        )
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    assert cards_route.call_count == 0, "Cart POST must NOT be called with malformed bounds"
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"


# ---------------------------------------------------------------------------
# fetch_observations — re-bootstrap on 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebootstrap_on_401() -> None:
    """401 on card-add triggers session re-bootstrap; current merchant gets no_data."""
    catalog = {27: _entry(27)}
    with respx.mock:
        # Session bootstrap (called twice: initial invocation + re-bootstrap after 401)
        session_route = respx.post(_SESSION_URL).mock(
            return_value=httpx.Response(
                200,
                headers={"set-cookie": "q3vsT1zXO=newjwt; Max-Age=1200"},
                json={"expiresInSeconds": 1199, "sessionId": "test-session"},
            )
        )
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(
            return_value=httpx.Response(401, json={"message": "Unauthorized"})
        )
        async with httpx.AsyncClient() as http:
            # Do NOT pre-set session_acquired_at so _ensure_session posts first
            cc = CardCashClient(http, per_request_sleep_s=0)
            cc._catalog = catalog
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    assert session_route.call_count == 2, (
        "Expected 2 session POSTs: initial bootstrap + re-bootstrap after 401"
    )
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"
    assert buy_obs.confidence == "none"


# ---------------------------------------------------------------------------
# fetch_observations — out-of-band percentage → low confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_side_low_confidence_out_of_band() -> None:
    """percentage → price_pct outside [0.20, 1.20] → confidence=low."""
    catalog = {27: _entry(27)}
    card_body = json.dumps(
        {
            "cartId": _CART_ID,
            "cards": [{"merchant": 27, "percentage": 10, "enterValue": 100}],  # 0.10 < 0.20
        }
    )
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=card_body))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.confidence == "low"
    assert buy_obs.availability == "available"
    assert buy_obs.price_pct == pytest.approx(0.10, abs=1e-9)


# ---------------------------------------------------------------------------
# fetch_observations — two observations per merchant (compose)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_observations_emits_both_channels() -> None:
    """fetch_observations returns exactly two observations: sell + buy channel."""
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    with respx.mock:
        respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
        respx.post(_CARDS_URL).mock(return_value=httpx.Response(201, text=_CARD_ADD_BODY))
        async with httpx.AsyncClient() as http:
            cc = _make_client(http, catalog=catalog)
            obs = await cc.fetch_observations(
                merchant_id="home-depot", source_key=27, observed_at=_T0
            )

    channels = {o.channel for o in obs}
    assert "sell" in channels
    assert channels & {"buy_electronic", "buy_mail"}, "Expected a buy-side channel"
    assert len(obs) == 2
    assert all(o.merchant_id == "home-depot" for o in obs)
    assert all(o.source_name == "cardcash" for o in obs)


# ---------------------------------------------------------------------------
# _post_card_with_retry — retry-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_429_then_201() -> None:
    """429 on first attempt → sleep(2.0) → 201 on second attempt → buy obs available."""
    catalog = {27: _entry(27)}
    responses = iter(
        [
            httpx.Response(429),
            httpx.Response(201, text=_CARD_ADD_BODY),
        ]
    )
    with patch(
        "zeal.ingestion.competitor.cardcash.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        with respx.mock:
            respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
            respx.post(_CARDS_URL).mock(side_effect=lambda req: next(responses))
            async with httpx.AsyncClient() as http:
                cc = _make_client(http, catalog=catalog)
                obs = await cc.fetch_observations(
                    merchant_id="merch-x", source_key=27, observed_at=_T0
                )

    mock_sleep.assert_any_await(2.0)
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "available"
    assert buy_obs.price_pct == pytest.approx(_HD_BUY_PRICE_PCT, abs=1e-9)


@pytest.mark.asyncio
async def test_retry_429_retry_after_header() -> None:
    """429 with Retry-After: 5 header → sleep(5.0) not sleep(2.0)."""
    catalog = {27: _entry(27)}
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "5"}),
            httpx.Response(201, text=_CARD_ADD_BODY),
        ]
    )
    with patch(
        "zeal.ingestion.competitor.cardcash.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        with respx.mock:
            respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
            respx.post(_CARDS_URL).mock(side_effect=lambda req: next(responses))
            async with httpx.AsyncClient() as http:
                cc = _make_client(http, catalog=catalog)
                await cc.fetch_observations(merchant_id="merch-x", source_key=27, observed_at=_T0)

    mock_sleep.assert_any_await(5.0)
    sleep_args = [call.args[0] for call in mock_sleep.await_args_list]
    assert 2.0 not in sleep_args, "Retry-After header should override the default backoff delay"


@pytest.mark.asyncio
async def test_retry_429_exhausted() -> None:
    """429 × 3 → no_data, exactly 3 card-add calls, no exception raised."""
    catalog = {27: _entry(27)}
    with patch("zeal.ingestion.competitor.cardcash.asyncio.sleep", new_callable=AsyncMock):
        with respx.mock:
            respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
            cards_route = respx.post(_CARDS_URL).mock(return_value=httpx.Response(429))
            async with httpx.AsyncClient() as http:
                cc = _make_client(http, catalog=catalog)
                obs = await cc.fetch_observations(
                    merchant_id="merch-x", source_key=27, observed_at=_T0
                )

    assert cards_route.call_count == 3, "Should attempt card-add exactly 3 times before giving up"
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"


@pytest.mark.asyncio
async def test_retry_5xx_then_201() -> None:
    """503 on first attempt → sleep(2.0) → 201 on second → buy obs available."""
    catalog = {27: _entry(27)}
    responses = iter(
        [
            httpx.Response(503),
            httpx.Response(201, text=_CARD_ADD_BODY),
        ]
    )
    with patch(
        "zeal.ingestion.competitor.cardcash.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        with respx.mock:
            respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
            respx.post(_CARDS_URL).mock(side_effect=lambda req: next(responses))
            async with httpx.AsyncClient() as http:
                cc = _make_client(http, catalog=catalog)
                obs = await cc.fetch_observations(
                    merchant_id="merch-x", source_key=27, observed_at=_T0
                )

    mock_sleep.assert_any_await(2.0)
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "available"
    assert buy_obs.price_pct == pytest.approx(_HD_BUY_PRICE_PCT, abs=1e-9)


@pytest.mark.asyncio
async def test_retry_5xx_exhausted() -> None:
    """503 × 2 → no_data, exactly 2 card-add calls, no exception raised."""
    catalog = {27: _entry(27)}
    with patch("zeal.ingestion.competitor.cardcash.asyncio.sleep", new_callable=AsyncMock):
        with respx.mock:
            respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
            cards_route = respx.post(_CARDS_URL).mock(return_value=httpx.Response(503))
            async with httpx.AsyncClient() as http:
                cc = _make_client(http, catalog=catalog)
                obs = await cc.fetch_observations(
                    merchant_id="merch-x", source_key=27, observed_at=_T0
                )

    assert cards_route.call_count == 2, "Should attempt card-add exactly 2 times before giving up"
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"


@pytest.mark.asyncio
async def test_retry_network_error_then_201() -> None:
    """ConnectError on first attempt → sleep(1.0) → 201 on second → buy obs available."""
    catalog = {27: _entry(27)}
    call_count = 0

    def _side_effect(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(201, text=_CARD_ADD_BODY)

    with patch(
        "zeal.ingestion.competitor.cardcash.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        with respx.mock:
            respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
            respx.post(_CARDS_URL).mock(side_effect=_side_effect)
            async with httpx.AsyncClient() as http:
                cc = _make_client(http, catalog=catalog)
                obs = await cc.fetch_observations(
                    merchant_id="merch-x", source_key=27, observed_at=_T0
                )

    mock_sleep.assert_any_await(1.0)
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "available"
    assert buy_obs.price_pct == pytest.approx(_HD_BUY_PRICE_PCT, abs=1e-9)


@pytest.mark.asyncio
async def test_retry_network_error_exhausted() -> None:
    """ConnectError × 2 → no_data, exactly 2 attempts, no exception raised."""
    catalog = {27: _entry(27)}
    call_count = 0

    def _side_effect(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("connection refused")

    with patch("zeal.ingestion.competitor.cardcash.asyncio.sleep", new_callable=AsyncMock):
        with respx.mock:
            respx.post(_CARTS_URL).mock(return_value=httpx.Response(201, text=_CART_CREATE_BODY))
            respx.post(_CARDS_URL).mock(side_effect=_side_effect)
            async with httpx.AsyncClient() as http:
                cc = _make_client(http, catalog=catalog)
                obs = await cc.fetch_observations(
                    merchant_id="merch-x", source_key=27, observed_at=_T0
                )

    assert call_count == 2, "Should attempt card-add exactly 2 times before giving up"
    buy_obs = next(o for o in obs if o.channel != "sell")
    assert buy_obs.availability == "no_data"
