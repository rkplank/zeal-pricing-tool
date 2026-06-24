# Competitor Scraper Design — CardCash v1

_Branch: feature/competitor-scrapers. Design-only document; no code is written here._

---

## 1. Goal and scope

Automatically collect CardCash gift-card rates and surface them on each merchant's detail page as **reference material only**. Competitor data in v1 is never an input to the pricing engine and never affects `ebay_weight`. The competitor refresh path does not call `compute_prices()`. The operator uses the data to sanity-check Zeal's recommendations against a known market participant.

**What this is not:**

- Not an input to the pricing engine. The competitor refresh path stores observations and displays them; it never invokes `compute_prices()`. The engine's blending path accepts a `CompetitorAggregate` argument, but v1 locks `ebay_weight = 1.0` for all merchants, so the blending path is never exercised. The correct future path — feeding observations through `aggregate_competitor_observations()` into `CompetitorAggregate` — is wired but inactive until `ebay_weight` is relaxed.
- Not blended. See above. Neither the engine nor the blending path is changed by this branch.
- Not a multi-source system yet. v1 builds exactly one source: CardCash. Raise and others are explicitly deferred to post-feedback work (per decisions_log.md 2026-05-04 and architecture.md §11 Phase 4).

---

## 2. What already exists — the scraper's output contract

The scraper must produce `CompetitorObservation` objects that pass through `aggregate_competitor_observations()` unchanged. The existing code defines the contract precisely.

### 2.1 CompetitorObservation fields

```
merchant_id    str                                        — must match merchants.merchant_id
source_name    str                                        — must be "cardcash" (literal; used as FK to competitor_sources)
channel        "buy_mail" | "buy_electronic" | "sell" | "marketplace_sell"
price_pct      float | None                               — fraction of face value, e.g. 0.87 means 87%
availability   "available" | "unavailable" | "no_data"
confidence     "high" | "medium" | "low" | "none"
observed_at    str                                        — ISO 8601 UTC, e.g. "2026-05-24T14:30:00Z"
source_url     str | None                                 — the CardCash page the rate was read from
raw_payload    str | None                                 — JSON-serialised raw parse data for debugging
```

`created_at` is a column default (`DEFAULT (datetime('now'))`) set by SQLite at insert time. The scraper must not set it.

### 2.2 Channel-to-field mapping (what aggregate_competitor_observations does)

```
"sell"             → CompetitorAggregate.online_sell
"marketplace_sell" → CompetitorAggregate.online_sell   (same field; both channels contribute)
"buy_mail"         → CompetitorAggregate.in_mail_buy
"buy_electronic"   → CompetitorAggregate.electronic_buy
```

CardCash exposes rates in two directions. The full channel set per merchant per run is:

| CardCash rate | Zeal channel | CompetitorAggregate field |
|---|---|---|
| Consumer-buy price (what a consumer pays CC to buy a card) | `sell` | `online_sell` |
| Mail-in offer (what CC pays for a card, physical delivery) | `buy_mail` | `in_mail_buy` |
| Electronic offer (what CC pays for a card, instant transfer) | `buy_electronic` | `electronic_buy` |

The scraper emits TWO observations per mapped merchant per run: one `sell` from the buy-side blob (§4.7), and one buy-side (`buy_electronic` or `buy_mail`) from the cart flow (§4.8). Never fabricate a channel from another.

### 2.3 Validity constraints from _is_valid()

An observation is silently dropped by `aggregate_competitor_observations()` if **any** of these are true:

- `availability != "available"`
- `confidence == "none"`
- `price_pct is None`
- `price_pct < 0.20` or `price_pct > 1.20`

The scraper should emit observations even when the card is unavailable or no rate was found — those become `availability="unavailable"` or `availability="no_data"` rows, which are stored for the display panel (so the operator sees "Not offered" rather than a blank row) but excluded from aggregation. The scraper should never emit `confidence="none"` for a successfully parsed rate; see §6 for confidence assignment rules.

---

## 3. The CompetitorClient interface

### 3.1 Protocol definition

Proposed module: `src/zeal/ingestion/competitor/base.py`

```python
# Sketch — not final code
from typing import Protocol
from datetime import datetime
from collections.abc import Sequence
from zeal.models.competitor import CompetitorObservation

class CompetitorClient(Protocol):
    async def fetch_observations(
        self,
        *,
        merchant_id: str,
        source_key: int,
        observed_at: datetime,
    ) -> list[CompetitorObservation]: ...

    @property
    def source_name(self) -> str: ...
```

`source_key` is the source-specific numeric identifier for this merchant — for CardCash, the `id` value from each blob `merchantsBuy.sortedByName` entry (stored on Zeal merchants as `merchants.cardcash_id`, e.g. 27 for Home Depot). Typed as `int` for v1 with CardCash as the sole source; when additional sources with non-numeric keys are added this would generalise to `str | int`. `merchant_id` is the Zeal internal id passed through so each returned observation has the correct `merchant_id`. `observed_at` is the single timestamp for all observations from this fetch call, passed in by the caller so a batch run is timestamped consistently.

The method returns all observations for the given merchant, one per channel found. It never raises on a parse failure or missing merchant — those become `availability="no_data"` observations (see §6).

### 3.2 Naming and the existing CompetitorSource model

`CompetitorSource` in `models/competitor.py` is a Pydantic model that mirrors the `competitor_sources` DB table — it is metadata about a source (active/inactive, refresh interval, last-run timestamps). **Do not repurpose or rename it.** The Python Protocol for scraper implementations is a different concept; naming it `CompetitorClient` keeps the distinction clear and mirrors the naming of `EbayClient` in `src/zeal/ingestion/ebay_client.py`.

The `SyntheticCompetitorClient` (a no-network stub for tests and future synthetic mode) would also implement this protocol.

---

## 4. The CardCash scraper design

### 4.1 Module

`src/zeal/ingestion/competitor/cardcash.py`

### 4.2 Fetch strategy

Follow the eBay client conventions exactly:

- Accept `http_client: httpx.AsyncClient` injected via the constructor. Never construct `httpx.AsyncClient` internally.
- All fetches are `async`; use `await http_client.get(url)`.
- No auth required for CardCash public pages.
- Apply a configurable per-request sleep (`per_request_sleep_s`, default 0.75) to avoid hammering CardCash. The per-request sleep applies to the per-merchant card-add POST loop (§4.5).
- Set a descriptive `User-Agent` header (see §9).
- The injected client must persist cookies across requests and must add the `x-cc-app: q3vsT1zXO` header on all `/v3/` calls.

The class is constructed once and reused across all merchants in a single run. The `http_client` lifetime is managed by the caller.

### 4.3 URL pattern

The buy page family and the sell-side API have both been captured and confirmed:

| Data needed | URL pattern |
|---|---|
| Buy catalog (consumer purchase, includes `upToPercentage` for all merchants) | `https://www.cardcash.com/buy-gift-cards/{slug}` |
| Session bootstrap (sets anonymous session cookie) | `https://production-api.cardcash.com/v3/session` |
| Create sell cart | `https://production-api.cardcash.com/v3/carts` |
| Add card to sell cart | `https://production-api.cardcash.com/v3/carts/{cartId}/cards` |

`{slug}` is the CardCash brand slug as it appears in the URL — e.g. `discount-home-depot-cards` for Home Depot. This is the full value of the `slug` field in `merchantsBuy.sortedByName` from `INITIAL_STATE` (see §4.4). For v1 a single buy-page GET retrieves the entire catalog, so `{slug}` can be any valid slug (the full `merchantsBuy.sortedByName` array is returned regardless of which page is requested). `{cartId}` is the cart identifier extracted from the cart-create response (see §4.5).

### 4.4 Buy-side reference (INITIAL_STATE blob)

CardCash's buy page (`/buy-gift-cards/{slug}`) is a server-rendered React app using loadable-components — not Next.js. A plain `GET` returns the SPA shell with a `<script id="injected-variables">` block that assigns `window.INITIAL_STATE = { … }`. This block contains the full buy catalog. The per-denomination rate table (precise rates per face-value denomination) is **not** in the HTML; it loads via a separate XHR call after page paint.

Playwright is **not required** — the `INITIAL_STATE` JSON is present in the raw GET response, parseable with a regex or `selectolax` text extraction without executing JavaScript.

One GET of any buy page returns `window.INITIAL_STATE`. The key `merchantsBuy.sortedByName` is an array covering the entire CardCash buy catalog. Each entry has:

```
id                int    — CardCash numeric merchant id (stored as merchants.cardcash_id)
slug              str    — URL/DB slug, e.g. "discount-home-depot-cards"
upToPercentage    float  — coarse MAX discount offered (not an average or typical rate)
cardType          str    — e.g. "physical", "ecode", "BOTH"
sellIsOff         int    — 1 if merchant is not accepting card sales, 0 otherwise (truthy int, not bool)
cardsAvailable    int    — inventory count (0 = none in stock, N = N cards available; falsy when 0)
maxFaceValue      float
minFaceValue      float
aliases           list[str]
```

The `upToPercentage` value maps to Zeal's `sell` channel / `CompetitorAggregate.online_sell`. It is the catalog-wide **maximum discount** offered by CardCash for this merchant — not an average or typical rate. Because it is the maximum discount, `price_pct = 1 - upToPercentage/100` is the **lowest** (best-case for the buyer) price CardCash could charge a consumer. Typical per-denomination prices are higher (less discount). This surface therefore **understates** the typical price a consumer pays — it provides an optimistic floor, not a central estimate. `confidence="medium"` reflects this coarse-max precision.

**Phase 2 verification required:** before trusting buy-side observations in production, confirm (1) the conversion direction: that `upToPercentage` is a discount in percentage-points (e.g. Home Depot = 1.6 means the consumer pays 98.4%, not 1.6% of face value), and (2) the unit: that the value is in percentage-points, not already a fraction. Verify against `tests/fixtures/cardcash/buy_catalog.html` and a live spot-check of one known merchant before the buy-side surface is trusted.

**Cost model:** one HTTP GET, regardless of catalog size. No per-merchant fetches. Total run time for this surface: a few seconds.

This is the first of two REQUIRED data paths for v1. Parsing details are in §4.7.

### 4.5 Sell-side reference (cart-driven flow)

The sell-side surface uses a stateful JSON API at `production-api.cardcash.com/v3/`. Unlike the buy-side blob (a single GET covers all merchants), the sell-side API requires a session cookie and a cart session per run. All `/v3/` requests must include the session cookie and the header `x-cc-app: q3vsT1zXO` (see §4.6).

The flow has four steps:

**Step 1 — Session bootstrap.** Covered in §4.6. Performed once per run before any `/v3/` call.

**Step 2 — Create cart.**

- POST `https://production-api.cardcash.com/v3/carts`
- Body: `{"action": "sell"}` (CardCash action name for "CardCash buys from the user"; `"buy"` is incorrect — it accepts the request but then rejects card-adds with a JSON schema validation error).
- Response 201; body:
  ```json
  {"cartId": "...", "cards": []}
  ```
- Extract `response["cartId"]` (flat — **not** `cart.sellCart.cartId`).

**Step 3 — Add card (per merchant).**

- POST `https://production-api.cardcash.com/v3/carts/{cartId}/cards`
- Headers: `x-cc-app: q3vsT1zXO`; `content-type: application/json`.
- Body:
  ```json
  {"card": {"merchantId": <int>, "enterValue": 100}}
  ```
  - `merchantId` is the CardCash numeric id from the blob's `id` field (e.g. 27 for Home Depot, 54 for Starbucks, 753 for 1-800-Flowers). Not the URL slug. Not the field named `merchant` in the response body.
  - `enterValue` is the balance to quote — standardize on `100` for v1 (comparability across merchants and runs). Before POSTing, read `minFaceValue` and `maxFaceValue` from the blob entry (§4.7 step 5 retains these). If 100 is outside `[minFaceValue, maxFaceValue]`, clamp: use `int(min(maxFaceValue, max(minFaceValue, 100)))`. If the blob entry has `minFaceValue > maxFaceValue` (malformed bounds), emit a `no_data` observation and skip the POST. **Phase 2 note:** verify real API behavior when `enterValue` is outside the merchant's face-value range — the clamp is a safety assumption, not a confirmed API response shape.
- Response 201; body:
  ```json
  {
    "cartId": "...",
    "cards": [
      {
        "id": <uuid>, "merchant": <int>, "merchantName": <str>,
        "enterValue": 100, "cashValue": "83.00", "percentage": 83,
        "number": null, "pin": null, "refId": <str>,
        "magStrip": null, "balanceVerified": false
      }
    ]
  }
  ```
- Locate the added card: find the entry in `response["cards"]` where `card["merchant"] == source_key` (the integer merchantId just POSTed). Do **not** use positional index `cards[-1]` — the cart accumulates entries across merchants in the same session, and positional reads risk cross-merchant contamination if the API ever reorders. Extract `percentage` from the matched entry.

**Step 4 — Cart accumulation.** The cart accumulates across POSTs within the same session — adding a second merchant produces a two-entry `cards` array under the same `cartId`. No reset between merchants is needed. No final GET `/v3/carts` readback is needed; each POST response contains the full current cart state.

**Cost model:** ~1 session bootstrap + ~1 cart create + N add-card POSTs (N = Zeal merchants with `cardcash_id IS NOT NULL` and `sellIsOff=false` in the blob). For ~300 merchants: ~303 requests, ~3–4 minutes at 750ms per-POST sleep.

This is the second of two REQUIRED data paths for v1. Parsing details are in §4.8.

### 4.6 Session bootstrap

Before any `/v3/` API call, acquire a session cookie:

1. POST `https://production-api.cardcash.com/v3/session` with an empty JSON body (`{}`) and header `x-cc-app: q3vsT1zXO`. The server sets `q3vsT1zXO=<JWT>` via `Set-Cookie` in the response. A cookie-jar-enabled httpx client carries the cookie on all subsequent `/v3/` calls automatically — no manual cookie injection and no `Authorization` header. The `x-cc-app: q3vsT1zXO` header value is the literal string `q3vsT1zXO` (an app identifier, not the JWT value), and must be sent on every `/v3/` request.
2. The JWT has a 20-minute expiry (`expiresInSeconds: ~1199`). A normal run of ~300 merchants at 750ms per-POST takes ~3–4 minutes — well within the session lifetime.
3. **Session resilience:** re-POST `/v3/session` if any `/v3/` call returns HTTP 401 or 403, or when 18 minutes have elapsed since bootstrap (2-minute safety margin before expiry). After re-bootstrap, recreate the cart — a new `cartId` is required because the old cartId is tied to the expired session — then resume the per-merchant loop at the next unprocessed merchant.
4. The session is anonymous — no login, no credentials.

If `zeal refresh-competitors` is invoked more than once within 20 minutes, each invocation bootstraps a new session independently — session state is not shared across CLI invocations.

**Total budget cap:** if total elapsed time since the run started reaches 40 minutes, abort the loop for remaining merchants and set run `status='partial'`. This prevents repeated re-bootstraps or one stalled merchant from extending a run indefinitely.

### 4.7 Parsing the INITIAL_STATE block

For the buy-side surface (§4.4), parse the catalog from the GET response:

1. Locate `<script id="injected-variables">` in the raw HTML.
2. Extract the JSON value from the `window.INITIAL_STATE = { … };` assignment. The recommended approach is `json.JSONDecoder().raw_decode()`: locate the first `{` after the `window.INITIAL_STATE` prefix (e.g. via `text.index('{', text.index('window.INITIAL_STATE'))`) and call `decoder.raw_decode(text, idx)` — it parses exactly one JSON value starting at that offset and ignores everything after the closing `}`, including the trailing `; maxmind_user_id = …` or other variable assignments that would cause a simple regex to terminate at a `};` inside the JSON. A non-greedy regex (`window\.INITIAL_STATE\s*=\s*(\{.*?\});` with `re.DOTALL`) is a fragile fallback: it can mis-terminate if any nested object ends with `};`.
3. `json.loads()` the object returned by `raw_decode()` (or the captured group if falling back to regex) to a dict.
4. Iterate `data["merchantsBuy"]["sortedByName"]` — one entry per merchant.
5. For each entry: extract `id`, `slug`, `upToPercentage`, `sellIsOff`, `cardsAvailable`, `cardType`.
6. Match to Zeal merchants via `merchants.cardcash_id = entry["id"]` (exact integer match; no fuzzy logic needed).
7. Determine `availability`:
   - `sellIsOff` truthy (i.e. `sellIsOff != 0`) → `"unavailable"`
   - `cardsAvailable` falsy (i.e. `cardsAvailable == 0`) → `"unavailable"`
   - Otherwise → `"available"`
8. Compute `price_pct` from `upToPercentage`. `upToPercentage` is a **discount percentage** — it represents how many percentage points off face value CardCash is offering (e.g. Home Depot = 1.6 means "1.6% off", so the consumer pays 98.4%). Conversion: `price_pct = 1 - (upToPercentage / 100)`. Example: `upToPercentage=1.6` → `price_pct=0.984`. `upToPercentage=0` means 0% off (consumer pays full face value) → `price_pct=1.0`; this is valid and must not be treated as unavailable — availability in the buy-side surface is determined by `sellIsOff`/`cardsAvailable` (step 7), not by the discount value. Validity guard: first sanity-check that `upToPercentage` is in `[0, 100]` (it is a percentage so negative or >100 is a data error); if outside that range, log a warning and set `confidence="low"`. Then validate the derived `price_pct` against the `[0.20, 1.20]` band from §2.3; if outside, log a warning and set `confidence="low"` (the observation is still stored for the display panel).
9. Store the matching entry dict (JSON-serialised) in `raw_payload` for operator debugging.
10. If a Zeal merchant's `cardcash_id` is not found in the catalog → emit a `sell` observation with `availability="no_data"`, `confidence="none"`, `price_pct=None`.
11. Retain the `cardType` field from each matched blob entry — it is needed by §4.8 for channel mapping in the sell flow.

If the `<script id="injected-variables">` block is absent or the JSON fails to parse, log a structured warning and raise `CompetitorClientError` — this is a scraper-level failure, not a per-merchant failure.

### 4.8 Sell-flow parsing

Companion to §4.7 for the sell-side cart flow (§4.5). Per-run processing:

1. **Bootstrap session.** POST to `https://production-api.cardcash.com/v3/session` with `{}` body and `x-cc-app: q3vsT1zXO` header (see §4.6 corrected). The same client instance carries the cookie on all subsequent calls.

2. **Create cart.** POST `/v3/carts` with body `{"action": "sell"}`; extract `cartId` from `response["cartId"]` (flat — not `response["cart"]["sellCart"]["cartId"]`).

3. **For each Zeal merchant** with `cardcash_id IS NOT NULL` where the blob entry (from §4.7) has `sellIsOff=false`:
   - Apply the `enterValue` clamp from §4.5 step 3 (clamp 100 to `[minFaceValue, maxFaceValue]` from the blob entry; emit `no_data` and skip this POST if bounds are malformed). POST `/v3/carts/{cartId}/cards` with body `{"card": {"merchantId": <source_key>, "enterValue": <clamped_value>}}`.
   - Locate the added card: find the entry in `response["cards"]` where `card["merchant"] == source_key` (the integer merchantId just POSTed). Do **not** use positional index `cards[-1]` — the cart accumulates entries across merchants in the same session, and positional reads risk cross-merchant contamination if the API ever reorders. Extract `percentage` from the matched entry.
   - Convert to `price_pct`: `price_pct = percentage / 100` (e.g. `percentage=83` → `price_pct=0.83`). This is the opposite direction from the buy-side conversion: `upToPercentage` is a discount deducted from face value, while `percentage` here is the seller's direct payout fraction.
   - Validate `price_pct ∈ [0.20, 1.20]` per §2.3; if outside, store with `confidence="low"`.
   - **Channel mapping** by the merchant's `cardType` field from the blob:
     - `cardType="ecode"` → `buy_electronic`
     - `cardType="physical"` → `buy_mail`
     - `cardType="BOTH"` → `buy_electronic` (v1 simplification; see O1)

4. **Skip on sellIsOff.** If a merchant's blob entry has `sellIsOff=true`: emit a `no_data` observation for the appropriate buy channel (determined by `cardType`); do not POST to the cart.

5. **Failure handling.**
   - Session bootstrap or cart create fails → raise `CompetitorClientError`; abort the run; no sell-flow observations are written.
   - Per-merchant POST returns non-201, raises a network error, or the response body is missing `percentage` → log; emit a `no_data` observation (`availability="no_data"`, `confidence="none"`, `price_pct=None`) for the buy channel; continue to the next merchant.

---

## 5. Merchant matching

Zeal merchants have `merchant_id` (internal slug, e.g. `"target"`) and `display_name` (e.g. `"Target"`). CardCash uses numeric merchant ids as the canonical sell-side identifier. These do not follow a predictable pattern relative to Zeal's IDs.

**Recommendation: `cardcash_id` column on `merchants` table (Option A)**

Add a nullable `INTEGER` column `cardcash_id` to `merchants`. A `NULL` means the merchant is not carried on CardCash or has not been mapped yet. During scraping, filter to `WHERE cardcash_id IS NOT NULL AND is_active = 1`. The operator populates this from the catalog.

- Pro: trivially queryable, no joins, single source of truth, explicit operator control.
- Pro: absent entry is unambiguous (NULL = not mapped; query still returns zero rows gracefully).
- Con: if 4+ sources are added, a separate `competitor_merchant_mapping` table becomes preferable. For 2–3 sources this is fine.

**How to populate:** the operator can derive `cardcash_id` values from a single INITIAL_STATE pull — one GET of any CardCash buy page yields every merchant in `merchantsBuy.sortedByName`. Each entry has `id` (the numeric id to store as `cardcash_id`), `slug`, `name`, and `aliases`. The operator matches these to Zeal merchants by display name and aliases offline (e.g. in a spreadsheet or a one-off script), then provides a CSV or direct SQL update. No per-merchant fetch is needed for this step; the whole catalog is in one response. Merchants with no CardCash equivalent simply keep `cardcash_id = NULL`.

The `slug` field remains available in the blob and is derivable from `cardcash_id` at any time via a single catalog fetch, if a future buy-precise per-denomination path ever needs URL construction from the slug.

**Schema application — see §10 Phase 1.**

---

## 6. Confidence and validity assignment

The scraper assigns `confidence` and `availability` at parse time.

| Situation | availability | confidence | price_pct |
|---|---|---|---|
| Buy blob: `upToPercentage` in `[0, 100]`, derived `price_pct` in `[0.20, 1.20]` (including `upToPercentage=0` → `price_pct=1.0`) | `"available"` | `"medium"` | derived float |
| Buy blob: `upToPercentage` outside `[0, 100]` OR derived `price_pct` outside `[0.20, 1.20]` | `"available"` | `"low"` | derived float |
| Buy blob: merchant found with `sellIsOff=True` or `cardsAvailable=False` | `"unavailable"` | `"medium"` | `None` |
| Buy blob: merchant `cardcash_id` not found in catalog | `"no_data"` | `"none"` | `None` |
| Sell flow: `percentage` returned, derived `price_pct ∈ [0.20, 1.20]` | `"available"` | `"high"` | derived float |
| Sell flow: `price_pct` derived outside `[0.20, 1.20]` | `"available"` | `"low"` | derived float |
| Sell flow: blob entry has `sellIsOff=true` | `"unavailable"` | `"medium"` | `None` |
| Sell flow: cart POST non-201 or `percentage` missing from response | `"no_data"` | `"none"` | `None` |
| HTTP error or network failure (not a parse issue) | Do not write an observation; log and skip. | — | — |

`confidence="medium"` for the buy-side blob reflects that `upToPercentage` is a catalog-wide maximum discount, not a per-denomination rate. Because it is the maximum discount, the derived `price_pct` is the lowest possible price — it **understates** the typical price a consumer pays (optimistic floor, not a central estimate). `confidence="high"` is reserved for sell-flow observations because their values are real per-merchant transactable rates at a standardized $100 balance, whereas the buy blob's `upToPercentage` is a catalog max.

A `confidence="none"` observation is valid to store (the display panel shows it); it is silently excluded by `_is_valid()` in aggregation.

Observations with `confidence="low"` are stored so the operator can see them in the panel; `_is_valid()` drops them from aggregation automatically. The scraper does not discard them — they may reflect real extreme or erroneous catalog entries.

**Two-concept confidence model.** The `confidence` field on a stored observation is the *source-quality* confidence — set immutably at parse time (table above), reflecting the precision of the raw data surface. A second concept, *effective confidence*, is the v2 design intent: source-quality degrades with observation age at read/aggregation time, not at storage time. In v1, `aggregate_competitor_observations()` uses stored confidence directly — the only recency control is a binary 30-day age cutoff that drops observations entirely; no decay schedule is applied. The scraper's responsibility is to set the stored source-quality value correctly at parse time; the aggregation layer will own the decay calculation when a second source or longer cadence makes recency degradation meaningful.

---

## 7. Run model

### 7.1 CLI command

```
uv run zeal refresh-competitors
```

Standalone command, independent of `ZEAL_EBAY_MODE`. Always runs regardless of whether the eBay path is in synthetic or live mode. Iterates active merchants with a non-null `cardcash_id`. Per-merchant failures log and skip (same pattern as `run_refresh()` in `refresh.py`).

### 7.2 Run tracking

**Recommendation: reuse `refresh_runs` with a `kind` discriminator column.**

Add `kind TEXT NOT NULL DEFAULT 'ebay' CHECK (kind IN ('ebay', 'competitor'))` to `refresh_runs`. eBay refresh inserts `kind='ebay'`, competitor refresh inserts `kind='competitor'`. The existing `status`, `processed`, `total`, `error`, `started_at`, `completed_at` columns all apply without change.

Rationale:
- The table structure is a perfect fit: status lifecycle, processed/total counter, error text are the same for both refresh types.
- The `kind` column costs one schema edit. A separate `competitor_refresh_runs` table with identical columns creates duplication and complicates "what is the latest run" queries.
- Querying is simple: `WHERE kind = 'competitor' ORDER BY started_at DESC LIMIT 1`.

**Schema application — see §10 Phase 1.**

### 7.3 Competitor refresh orchestrator

Proposed module: `src/zeal/ingestion/competitor/refresh.py`

```python
# Sketch — not final code
async def run_competitor_refresh(
    *,
    db: sqlite3.Connection,
    client: CompetitorClient,
    now: datetime | None = None,
) -> CompetitorRefreshSummary: ...
```

The orchestrator is a thin per-merchant loop, identical in shape to `run_refresh()` in `refresh.py`. The five-step buy+sell flow (bootstrap, blob fetch, cart create, per-merchant POSTs, no cleanup) is implemented inside `CardCashClient` and amortised across calls via lazy initialization — see §4.5–§4.8 for the client-internal details.

Orchestrator responsibilities:
- Insert a `refresh_runs` row with `kind='competitor'`, `status='running'`.
- Iterate Zeal merchants with `cardcash_id IS NOT NULL AND is_active = 1`.
- For each merchant: `await client.fetch_observations(merchant_id=..., source_key=..., observed_at=now)` → returns 1–2 observations (one `sell`-channel derived from the cached blob entry, one `buy_electronic`/`buy_mail` from the cart POST). Insert all returned observations.
- Update `competitor_sources.last_attempted_refresh` on every run; update `last_successful_refresh` only when the run completes successfully.

Failure handling:
- `CompetitorClientError` raised by the client (catastrophic — session bootstrap, blob parse, or cart create failed; this can only happen on the first per-merchant call of a run via lazy init) → set run `status='failed'`, no further merchants processed, abort.
- Any other per-merchant exception → log, increment error counter, continue.
- Final status: `completed` (0 errors), `partial` (some errors), `failed` (catastrophic abort).

The `competitor_sources` row for `"cardcash"` must exist before the first run (seeded as part of the schema seed step, not created dynamically).

---

## 8. Testing strategy

**No live network in tests.** All tests use static HTML fixture files served via `respx` (the existing HTTP mocking library used for eBay tests). This mirrors the `respx` discipline in `tests/test_ebay_marketplace_insights_client.py` and `tests/test_ebay_oauth.py`.

### 8.1 Fixture directory layout

```
tests/
    fixtures/
        cardcash/
            buy_catalog.html              # any /buy-gift-cards/{slug} page — contains full INITIAL_STATE catalog
            buy_catalog_partial.html      # variant with some merchants showing sellIsOff/cardsAvailable=false
            notfound_slug.html            # a GET response for an unrecognised slug (404 or redirect)
            cart_create_response.json     # POST /v3/carts 201 body (cart with empty sellCart.cards)
            card_add_response.json        # POST /v3/carts/{cartId}/cards 201 body (representative cards array)
```

The session-bootstrap step needs no separate fixture in unit tests; tests inject a pre-cookied client via `respx`.

Under the buy-side surface, a single catalog fixture covers all merchants in one parse, so per-merchant HTML files are not needed. Tests parameterise over entries extracted from `merchantsBuy.sortedByName`.

### 8.2 Test files

```
tests/
    test_cardcash_scraper.py       # unit tests: catalog parse, sell flow, edge cases per entry
    test_competitor_refresh.py     # integration tests: full orchestrator loop against mock DB
```

`test_cardcash_scraper.py` covers:

Buy-side blob:
- Happy path: catalog parsed, correct `price_pct` (derived as `1 - upToPercentage/100`), `confidence="medium"`, `availability="available"` for a mapped merchant.
- Merchant with `sellIsOff=True`: correct `availability="unavailable"`.
- Merchant with `cardsAvailable=False`: correct `availability="unavailable"`.
- Merchant id not found in catalog: correct `availability="no_data"` observation.
- Price out of range: stored with `confidence="low"`, correct `price_pct`.
- INITIAL_STATE block absent or malformed JSON: raises `CompetitorClientError`, does not silently return empty.

Sell-side cart flow:
- Happy path: cart created, card added, correct `price_pct` (derived as `percentage / 100`), `confidence="high"`, correct channel by `cardType` (`ecode` → `buy_electronic`, `physical` → `buy_mail`, `BOTH` → `buy_electronic`).
- Merchant with `sellIsOff=True` in blob: no cart POST issued; `no_data` observation emitted for the buy channel.
- Cart POST returns non-201: per-merchant `no_data` observation emitted, run continues.
- Cart POST response missing `percentage` key: per-merchant `no_data`, run continues.
- Cart create fails (non-201 or network error): raises `CompetitorClientError`.

`test_competitor_refresh.py` covers:
- Full loop: two merchants succeed, one fails; final status is `partial`.
- `refresh_runs` row created and updated correctly (including `kind='competitor'`).
- `competitor_sources.last_successful_refresh` updated on success.
- `competitor_sources.last_attempted_refresh` always updated.
- `competitor_observations` rows inserted with correct `merchant_id`, `source_name`, `channel`.

### 8.3 Fixtures the operator must capture

**Already captured:**
- One CardCash buy page (confirmed to contain `INITIAL_STATE`). This is sufficient to build and test the buy-side `sell` channel.
- One cart-create 201 response and one card-add 201 response (operator DevTools captures).

**Still needed before Phase 2 can close:**
1. Save the captured buy page verbatim as `tests/fixtures/cardcash/buy_catalog.html`. This becomes the primary test fixture.
2. Save the cart-create 201 body as `tests/fixtures/cardcash/cart_create_response.json`.
3. Save the card-add 201 body (the full `cards` array response) as `tests/fixtures/cardcash/card_add_response.json`.
4. If the catalog contains merchants with `sellIsOff=True` or `cardsAvailable=False`, those entries in the fixture are sufficient for unavailability tests — no separate "unavailable" page needed.

---

## 9. Politeness and robustness

**v1 cost model:** ~1 session bootstrap (POST `https://production-api.cardcash.com/v3/session`) + ~1 buy-side blob GET + ~1 cart create + N add-card POSTs (N = Zeal merchants with `cardcash_id IS NOT NULL` and `sellIsOff=0`). For ~300 merchants: ~303 requests, ~3–4 minutes per run at 750ms per-POST sleep. The per-request sleep now applies to a real per-merchant loop, not a single GET. The session JWT's 20-minute expiry comfortably covers this. The scraper appears to CardCash as a fresh anonymous shopper each run (new anonymous session per invocation); rate-limit posture is worth monitoring in early runs (O3).

**User-Agent:** use a realistic browser UA string (e.g. `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36`). Do not use Python's default `python-httpx/...` UA — it is trivially blocked.

**Canary invariants.** Before processing the catalog or emitting any observations, verify: (1) `merchantsBuy.sortedByName` contains more than 100 entries — a substantially smaller result indicates a truncated or structurally broken response; (2) at least one well-known anchor merchant is present and plausible — e.g. Home Depot (`id=27`) or Starbucks (`id=54`) appears in the array and its `upToPercentage` is in `[0, 100]`; (3) required field types are correct — `id` is `int`, `upToPercentage` is `float` or `int`, `sellIsOff` is `int` (0 or 1). On any invariant failure, raise `CompetitorClientError` — no observations are written for any merchant. Canary failures signal a scraper-level structural change (schema rename, response format shift), not a per-merchant data issue.

**Retry/backoff:** mirror the eBay client's `_get_with_retry` pattern:
- HTTP 429 → respect `Retry-After` header if present; otherwise back off exponentially (2s, 4s, 8s) up to 3 attempts, then raise `CompetitorRateLimitError`.
- HTTP 5xx → one retry after 2s, then raise `CompetitorServerError`.
- Network error (`httpx.RequestError`) → one retry after 1s, then raise `CompetitorNetworkError`.
- HTTP 404 → not an error; treat as `availability="no_data"` and return normally.
- All other 4xx → raise `CompetitorClientError`.

**INITIAL_STATE block absent:** log a structured warning and raise `CompetitorClientError` — this affects the whole run, not a single merchant.

**Merchant not found in catalog:** return one `no_data` observation for the `sell` channel (`price_pct=None`, `availability="no_data"`, `confidence="none"`). The buy-side channel (`buy_electronic` or `buy_mail`) is handled separately in §4.8.

**CardCash HTML structure changes:** if the `<script id="injected-variables">` selector fails or the INITIAL_STATE JSON schema changes (e.g. `merchantsBuy.sortedByName` key renamed), log a structured warning and raise `CompetitorClientError`. The per-merchant error handling in the refresh orchestrator catches any raises from individual merchant processing.

---

## 10. Phasing

The implementation is broken into six independently-testable phases:

**Phase 1 — Interface, model wiring, and schema**

Schema changes are made by editing `src/zeal/db/schema.sql` directly — two additions:

1. Add `cardcash_id INTEGER` (nullable) to the `merchants` table `CREATE TABLE` statement.
2. Add `kind TEXT NOT NULL DEFAULT 'ebay' CHECK (kind IN ('ebay', 'competitor'))` to the `refresh_runs` table `CREATE TABLE` statement.

There is no migration runner in this repo. `apply_schema()` in `src/zeal/db/connection.py` runs `schema.sql` via `conn.executescript()`, which uses `CREATE TABLE IF NOT EXISTS`. This means edits to `schema.sql` affect only freshly created databases — they do not alter existing `data/zeal.db` tables in place via `ALTER TABLE`.

**Application path for the existing `data/zeal.db`:** delete the file and re-seed from scratch:

```powershell
Remove-Item data\zeal.db
uv run zeal seed
```

`uv run zeal seed` is sufficient as a single step. Verified in `src/zeal/cli.py` `cmd_seed()`: it calls `apply_schema(conn)` before `seed_demo_data()`, so both schema application and seeding happen in one command. A separate `zeal init-db` call is not required. `seed_demo_data()` re-seeds from `tests/fixtures/spreadsheet_baseline.json`. This is lossless in the current state:
- `competitor_observations` is empty (no scraper has run yet).
- `refresh_runs` contains only synthetic run logs, which are re-created by `seed_demo_data()`.
- No operator-entered data (e.g. merchant config edits, live eBay observations) has been recorded to a production `zeal.db` at this stage.

> **Documentation inconsistency reconciled in this task:** `CLAUDE.md` (Database section) and `AGENTS.md` (Database section) previously stated that the canonical schema is "`schema.sql` plus numbered migrations in `src/zeal/db/migrations/`". That directory does not exist. The repo uses `schema.sql` only, applied idempotently by `apply_schema()`. `architecture.md §9.3` correctly describes the actual update process ("apply the migration SQL manually or re-seed into a fresh DB"). Both `CLAUDE.md` and `AGENTS.md` are corrected in this task to remove the migrations reference and align with the actual behavior.

Other Phase 1 deliverables:
- `src/zeal/ingestion/competitor/__init__.py`
- `src/zeal/ingestion/competitor/base.py` — `CompetitorClient` Protocol
- `src/zeal/ingestion/competitor/errors.py` — `CompetitorRateLimitError`, `CompetitorNetworkError`, `CompetitorClientError`, `CompetitorServerError`
- Seed `competitor_sources` row for `"cardcash"` (in `seed.py` or a separate seed script)
- All existing tests still pass; no scraper logic yet.

**Phase 2 — Scraper against fixtures**

- Operator saves the captured buy-page HTML as `tests/fixtures/cardcash/buy_catalog.html`.
- Operator saves the captured cart-create 201 body as `tests/fixtures/cardcash/cart_create_response.json`.
- Operator saves the captured card-add 201 body as `tests/fixtures/cardcash/card_add_response.json`.
- `src/zeal/ingestion/competitor/cardcash.py` — `CardCashClient` implementing `CompetitorClient`; both the buy-blob parser (§4.7) and the cart-driven sell client (§4.8) must be complete. Both surfaces must work before Phase 4 can ship a functional `zeal refresh-competitors`.
- `tests/test_cardcash_scraper.py` — full coverage against fixtures for both surfaces. Session-bootstrap step has no separate fixture; tests inject a pre-cookied client via `respx`.
- **upToPercentage semantic gate (required before Phase 4).** Using `buy_catalog.html`, confirm (a) that `upToPercentage` is a discount in percentage-points (e.g. Home Depot = 1.6 → consumer pays 98.4%) and not an already-normalized fraction, and (b) that `price_pct = 1 - upToPercentage/100` yields a plausible price. Cross-check one known merchant against a live spot-check. Do not ship Phase 4 until this is confirmed and the result documented in `decisions_log.md`.

**Phase 3 — Merchant matching**

- Operator derives `cardcash_id` values offline from one INITIAL_STATE pull (matching `name`/`aliases` to Zeal merchants by display name, using the numeric `id` from each blob entry) and provides a CSV or direct SQL update.
- Seed or update script to populate `merchants.cardcash_id`.
- Tests for the id lookup query.

**Phase 4 — CLI command and run tracking**

**Hard gate before first live run.** The Phase 1 schema changes (`cardcash_id` on `merchants`, `kind` discriminator on `refresh_runs`) are applied via `schema.sql` + delete-and-reseed (see §10 Phase 1). Before Phase 4 runs against a production `data/zeal.db` that may already hold operator-entered merchant config edits or live eBay observations, one of the following must be confirmed: (a) a manual `ALTER TABLE` path exists to add the new columns to the existing DB without data loss, or (b) a backup/export of `competitor_observations` and any operator-entered merchant config data is taken before re-seeding. Do not run `zeal refresh-competitors` live until one of these paths is confirmed and documented.

- `src/zeal/ingestion/competitor/refresh.py` — `run_competitor_refresh()` orchestrator.
- `zeal refresh-competitors` CLI entry point (wire into `src/zeal/cli.py`).
- `tests/test_competitor_refresh.py` — orchestrator tests with mock DB and mock client.

**Phase 5 — Display wiring**

- Repository query: `get_competitor_observations(db, merchant_id)` — returns most-recent observation per channel, sorted by `observed_at DESC`.
- Wire into the merchant detail route (the `competitor_panel.html` partial already exists and already iterates `merchant.competitor_observations`).
- Verify the competitor panel renders after a `zeal refresh-competitors` run.

**Phase 6 — Docs and acceptance**

- Update `docs/architecture.md` §4 (component map), §5 (refresh flow), §11 (phase status).
- Update `CLAUDE.md` current phase/status block.
- Verify acceptance criteria from architecture.md §11 Phase 4: after a refresh, CardCash rates appear on merchant detail for active merchants; recommendation is unchanged.

---

## 11. Open questions for the operator

**O1 — Physical-card merchant cart behavior.** The captures covered ecode merchants (Home Depot, Starbucks, 1-800-Flowers). For merchants with `cardType=physical` in the blob, confirm in Phase 2 (or on the first live run) that the same cart POST flow returns a single `percentage`. If CardCash asks for a delivery method or returns a different rate shape for physical cards, the `buy_mail` mapping may need adjustment. Not blocking design or initial implementation.

**O2 — Merchant matching (gates Phase 3).** For each of the ~300 active merchants, does the operator want to derive `cardcash_id` values manually from the INITIAL_STATE catalog (one GET yields the full list with numeric `id` for each entry), or run a first-pass fuzzy match by display name/aliases for review? The mapping does not need to be complete on day one — merchants with `cardcash_id IS NULL` are simply skipped.

**O3 — Rate-limit posture.** v1 makes ~303 requests per run (~1 session bootstrap + ~1 blob GET + ~1 cart create + ~300 card-add POSTs at 750ms per-POST). After the first live run, check for HTTP 429 responses and adjust `per_request_sleep_s` if needed. The scraper registers as a fresh anonymous shopper each run; the POST volume is the primary concern.

**O4 — Resolved.** Playwright is not required. The INITIAL_STATE JSON is present in the raw GET response and is parseable without executing JavaScript. The page uses loadable-components React, not Next.js, so there is no `__NEXT_DATA__` tag; the correct extraction point is `<script id="injected-variables">`.
