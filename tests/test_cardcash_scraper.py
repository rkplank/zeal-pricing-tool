"""Buy-blob parser tests for CardCashClient (Prompt 2a).

Sell-side cart flow (§4.5/§4.6/§4.8) is deferred to Prompt 2b.

Firewall-derived literals (hand-computed from real fixture 2026-06-14):
  Home Depot (id=27):  upToPercentage=2   → price_pct = 1 - 2/100   = 0.98
  Starbucks  (id=54):  upToPercentage=5.6 → price_pct = 1 - 5.6/100 = 0.944
"""
from __future__ import annotations

import asyncio
import json
import pathlib
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from zeal.ingestion.competitor.cardcash import CardCashClient
from zeal.ingestion.competitor.errors import CompetitorClientError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIXTURE_DIR = pathlib.Path("tests/fixtures/cardcash")
_BUY_HTML = (_FIXTURE_DIR / "buy_catalog.html").read_text(encoding="utf-8")
_T0 = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)

# Firewall-baked literals — never computed by importing the module under test.
_HD_PRICE_PCT = 0.98   # Home Depot  id=27  upToPercentage=2    1-2/100
_SB_PRICE_PCT = 0.944  # Starbucks   id=54  upToPercentage=5.6  1-5.6/100

# ---------------------------------------------------------------------------
# Constructed-fixture helpers (for branches not naturally present in the real file)
# ---------------------------------------------------------------------------


def _entry(
    id_: int,
    up_to: float | int = 5.0,
    sell_is_off: int = 0,
    cards_avail: int = 10,
    card_type: str = "ecode",
) -> dict[str, Any]:
    return {
        "id": id_,
        "slug": f"test-merchant-{id_}",
        "upToPercentage": up_to,
        "sellIsOff": sell_is_off,
        "cardsAvailable": cards_avail,
        "cardType": card_type,
        "minFaceValue": 5.0,
        "maxFaceValue": 500.0,
        "aliases": [],
    }


def _html(entries: list[dict[str, Any]]) -> str:
    blob = {"merchantsBuy": {"sortedByName": entries}}
    return (
        f'<script id="injected-variables">window.INITIAL_STATE = {json.dumps(blob)};</script>'
    )


# 101 generic entries that satisfy the count canary — used in canary tests that need
# a valid-length catalog but want to control specific entries.
_GENERIC_101 = [_entry(1000 + i) for i in range(101)]


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
    assert obs.price_pct == pytest.approx(_HD_PRICE_PCT, abs=1e-9)
    assert obs.raw_payload is not None
    payload = json.loads(obs.raw_payload)
    assert payload["id"] == 27
    assert "cardType" in payload  # retained for Prompt 2b channel mapping


def test_sell_observation_starbucks() -> None:
    catalog = CardCashClient.parse_catalog(_BUY_HTML)
    obs = CardCashClient.sell_observation(
        catalog[54], merchant_id="starbucks", source_key=54, observed_at=_T0
    )
    assert obs.availability == "available"
    assert obs.confidence == "medium"
    assert obs.price_pct == pytest.approx(_SB_PRICE_PCT, abs=1e-9)


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
# fetch_observations stub
# ---------------------------------------------------------------------------


def test_fetch_observations_not_implemented() -> None:
    client = CardCashClient(httpx.AsyncClient())
    with pytest.raises(NotImplementedError, match="Prompt 2b"):
        asyncio.run(
            client.fetch_observations(merchant_id="x", source_key=27, observed_at=_T0)
        )
