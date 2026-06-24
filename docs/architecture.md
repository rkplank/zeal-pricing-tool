# Zeal Pricing Tool — Architecture

**Status:** Draft for review — v1 scope realigned 2026-05-09
**Companion to:** `pricing_algorithm.md`
**Last updated:** 2026-05-09

This document specifies how the v1 pricing tool is built and deployed. It assumes the algorithm spec is the source of truth for *what* the system computes; this doc covers *how*.

---

## 1. Goals and non-goals

**Goals:**
- A working pricing dashboard the operator runs on demand to review pricing for ~300 merchants
- A narrow one-merchant-at-a-time config editor for formula/config inputs, with history logging
- Faithful implementation of the algorithm spec: spreadsheet-faithful recommendations from the eBay-only path
- Continuous historical record of every recommendation the tool has ever produced
- Competitor data displayed alongside recommendations as reference material (single source in v1, expandable to more)
- Easy for one developer to maintain (no exotic dependencies, no surprise complexity)
- Forward-compatible with future website integration: the pure-function engine boundary in `src/zeal/pricing/` stays protected so another consumer can import the pricing engine without the local dashboard

**Non-goals:**
- Multi-user support
- Hosted/SaaS deployment
- Mobile app or responsive design beyond "looks fine on a laptop"
- Automated price publishing
- Operator action tracking
- Scheduled refresh
- Global constants editing
- Bulk merchant configuration editing
- Automated competitor source discovery
- Website integration as a v1 feature

---

## 2. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 (python.org CPython) | Best ecosystem for HTTP scraping, data handling, eBay API. Must use the python.org installer (not uv-managed python-build-standalone): the python.org Windows build includes the OpenSSL applink shim required for correct TLS on Windows. |
| Web framework | FastAPI | Modern, async-capable, well-documented, plays nicely with HTMX |
| Templating | Jinja2 | Standard for FastAPI server-rendered pages |
| Frontend | HTMX + Tailwind | Server-rendered HTML with minimal JS; right complexity for a one-user dashboard |
| Database | SQLite | Single file, zero config, plenty for one user x ~300 merchants |
| HTTP client | httpx | Async, modern, replaces requests |
| HTML parsing | selectolax or BeautifulSoup4 | For CardCash scraping. selectolax preferred (faster, lower memory). |
| Validation | Pydantic v2 | Built into FastAPI; defines all data shapes |
| Env management | uv | Fastest tool, single binary, replaces pip/venv/poetry |
| Testing | pytest + pytest-asyncio | Standard |
| Linting/formatting | ruff | Replaces black, isort, flake8 in one tool |

Versions are floors, not ceilings. We pin in `pyproject.toml`.

---

## 3. Repository layout

```
zeal-pricing-tool/
├── README.md
├── CLAUDE.md
├── AGENTS.md
├── pyproject.toml
├── uv.lock
├── .python-version             # 3.12
├── .env.example
├── .gitignore
├── docs/
│   ├── pricing_algorithm.md
│   ├── architecture.md
│   ├── decisions_log.md
│   ├── spreadsheet_recon.md
│   ├── credential_day_validation_plan.md
│   ├── dashboard_usability_review_plan.md
│   ├── operator_demo_script.md
│   ├── historical_pricing_findings.md
│   └── historical_pricing_analysis.md
├── src/zeal/
│   ├── __init__.py
│   ├── config.py               # ZealConfig; reads ZEAL_EBAY_MODE, EBAY_* from env
│   ├── cli.py                  # `zeal serve`, `zeal seed`, `zeal seed-demo`, `zeal init-db`, `zeal smoke-ebay`
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql          # canonical schema; apply via apply_schema()
│   │   ├── connection.py       # get_connection(), apply_schema()
│   │   ├── repositories.py     # all query and mutation functions
│   │   └── seed.py             # seeds baseline fixture + synthetic recommendations
│   ├── models/
│   │   ├── merchant.py         # MerchantConfig, MerchantRecord
│   │   ├── pricing.py          # GlobalConstants, CompetitorAggregate, PriceRecommendation
│   │   ├── ebay.py             # EbaySoldListing, EbayObservation, EbaySummary
│   │   └── competitor.py       # CompetitorSource, CompetitorObservation
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── ebay_client.py      # EbayClient protocol + SyntheticEbayClient
│   │   ├── ebay_client_factory.py  # create_ebay_client(): synthetic or live by config
│   │   ├── ebay_errors.py      # EbayAuthError, EbayRateLimitError, etc.
│   │   ├── ebay_marketplace_insights_client.py  # live Marketplace Insights client
│   │   ├── ebay_oauth.py       # EbayTokenManager; OAuth2 client-credentials flow
│   │   └── refresh.py          # run_refresh() orchestrator; per-merchant eBay → recs loop
│   │   # Note: automated competitor scraper (CardCash) is NOT yet implemented.
│   │   # Competitor data schema is present; scraper is a planned v2 addition.
│   ├── pricing/
│   │   ├── __init__.py
│   │   ├── ebay_average.py     # compute_ebay_average() — spec §6.3
│   │   ├── listing_filter.py   # filter_listings() — spec §6.2; pure
│   │   ├── competitor_aggregate.py  # aggregate_competitor_observations() — spec §7
│   │   ├── confidence.py       # score_confidence() — spec §6.4
│   │   ├── blending.py         # blend_values(); used when ebay_weight < 1.0
│   │   └── engine.py           # compute_prices() — spec §5; four channel formulas
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI app factory; lifespan wiring
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── dashboard.py    # GET / — pricing list
│   │   │   ├── merchant.py     # GET /merchant/{id}, GET/POST /merchant/{id}/config
│   │   │   └── refresh.py      # POST /refresh, GET /refresh/status
│   │   ├── templating.py       # Jinja2 env + custom filters (pct, pp, channel, datetime, …)
│   │   ├── templates/
│   │   │   ├── base.html       # shared layout; HTMX loaded via CDN
│   │   │   ├── dashboard.html  # pricing list table
│   │   │   ├── merchant_detail.html  # detail: cards, chart, breakdown, observations
│   │   │   ├── merchant_config.html  # config edit form
│   │   │   └── partials/
│   │   │       ├── breakdown.html
│   │   │       ├── competitor_panel.html
│   │   │       ├── refresh_idle.html
│   │   │       └── refresh_running.html
│   │   └── static/
│   │       └── style.css
│   └── jobs/                   # placeholder; v1 has no scheduled jobs
├── tests/
│   ├── conftest.py
│   ├── test_pricing_engine.py
│   ├── test_pricing_engine_baseline.py  # 281 golden records at ±0.001
│   ├── test_ebay_average.py
│   ├── test_confidence.py
│   ├── test_listing_filter.py
│   ├── test_pricing_blending.py
│   ├── test_competitor_aggregate.py
│   ├── test_spreadsheet_parser.py
│   ├── test_models_merchant.py
│   ├── test_config.py
│   ├── test_db_schema.py
│   ├── test_repositories.py
│   ├── test_ebay_client_factory.py
│   ├── test_ebay_marketplace_insights_client.py
│   ├── test_ebay_oauth.py
│   ├── test_refresh_orchestrator.py
│   ├── test_refresh_routes.py
│   ├── test_web_routes.py
│   ├── test_template_filters.py
│   ├── test_seed_demo.py
│   ├── test_smoke_ebay_cli.py
│   ├── test_historical_spreadsheet_recon.py
│   └── fixtures/
│       └── spreadsheet_baseline.json
├── scripts/
│   ├── extract_baseline.py
│   ├── historical_spreadsheet_recon.py
│   └── spreadsheet_parser.py
└── data/                       # gitignored; runtime SQLite lives here
```

The split between `ingestion`, `pricing`, and `web` matters. The algorithm code (`pricing/`) has zero dependencies on web framework, database, or HTTP clients, which means it is testable and can be reused in a future website integration without rework. `listing_filter.py`, `competitor_aggregate.py`, and `blending.py` live in `pricing/` because they are pure functions with no I/O.

---

## 4. Component map

Four components, with explicit dependencies:

```
       ┌─────────────────────────────────┐
       │     Operator browser            │
       │       (localhost:8000)          │
       └─────────────────┬───────────────┘
                         ▼
       ┌─────────────────────────────────┐
       │       Dashboard (FastAPI)       │
       │            (web/)               │
       │  ┌───────────────────────────┐  │
       │  │ Background refresh task   │  │
       │  │ (in-process coroutine)    │  │
       │  └─────────────┬─────────────┘  │
       └────────────────┼────────────────┘
                        │
            ┌───────────┴────────────┐
            ▼                        ▼
   ┌──────────────────┐   ┌──────────────────┐
   │  Ingestion        │   │  Pricing Engine   │
   │  (ingestion/)     │──▶│  (pricing/)       │
   │  eBay (live/syn.) │   │  pure functions   │
   └────────┬──────────┘   └─────────┬─────────┘
            │                        │
            ▼                        ▼
       ┌────────────────────────────────┐
       │         SQLite Database         │
       │            (db/)                │
       │  Recommendations are append-    │
       │  only and form the historical   │
       │  record of all pricing data.    │
       └────────────────────────────────┘
```

**Component responsibilities:**

1. **Pricing Engine** — pure functions, no I/O. Reads merchant config, eBay observations, and competitor aggregates from arguments; returns `PriceRecommendation` objects with per-channel breakdowns. The formulas from spec §5 live here. The engine's input contract includes `ebay_weight` and a `CompetitorAggregate`; in v1 these are passed but `ebay_weight = 1.0` so the recommendation equals the eBay-only path output. Heavily tested. **Forward-compatibility note:** because this layer has no FastAPI or SQLite imports, a future website integration can import `compute_prices` directly without dragging the dashboard infrastructure with it.

2. **Ingestion** — eBay client (Marketplace Insights API wrapper, or `SyntheticEbayClient` when `ZEAL_EBAY_MODE=synthetic`) and the refresh orchestrator. The eBay client paginates, filters listings per spec §6.2, and writes to `ebay_observations` with `validity_status` and `exclusion_reason`. An automated competitor scraper is not yet implemented; competitor observations can be inserted manually or will be added by a v2 scraper. The competitor data schema and aggregation logic are present.

3. **Dashboard (FastAPI)** — the operator UI plus refresh orchestration. Two screens (list view, merchant detail) plus three control routes (`POST /refresh`, `GET /refresh/status`, `GET /merchant/{id}`). The refresh task runs as a FastAPI background task in the same process; status is tracked in the `refresh_runs` table and exposed via the status endpoint.

4. **Database** — SQLite at `data/zeal.db`. Schema in §6. The `price_recommendations` table is append-only and forms the system of record for all pricing recommendations the tool has ever produced.

---

## 5. Refresh data flow

Refresh is on-demand only. There is no scheduled job in v1.

**What happens when the operator clicks "Refresh now":**

1. Browser issues `POST /refresh`. Server checks `refresh_runs` for an in-flight run; if one exists, returns 409. Otherwise creates a row in `refresh_runs` with status `running` and dispatches a FastAPI background task.
2. Browser begins polling `GET /refresh/status` every 2 seconds. The status response is `{state, processed, total, started_at, error?}`.
3. The background task iterates active merchants:
   - For each merchant: query eBay Marketplace Insights API for sold listings matching the merchant's regex, last 90 days, US only. In synthetic mode, returns seeded data without network calls.
   - For each listing: apply validity filters (spec §6.2), upsert into `ebay_observations` (deduped by `listing_id`), recording `validity_status` and `exclusion_reason`.
   - Compute `ebay_sell_pct` per spec §6.3, eBay confidence per spec §6.4. Upsert one row in `ebay_summary` keyed by `(merchant_id, today)`.
   - Compute the recommendation by calling `compute_prices(ebay_sell_pct, ebay_confidence, competitor=CompetitorAggregate(), config, constants)`. v1 always passes `ebay_weight = 1.0` (read from merchant config) and the recommendation equals the eBay-only output. Insert into `price_recommendations`.
   - Update the `refresh_runs` row's `processed` count.
   - Merchants with `online_sell_override` set skip the eBay fetch and compute directly from the override value.
4. When all merchants are processed (or an unrecoverable error occurs): mark `refresh_runs` row `completed` (or `failed`/`partial`), set `completed_at`. The status endpoint surfaces this and the browser stops polling.
5. The dashboard re-renders the list view to show the new recommendations.

**Note — competitor refresh:** an automated competitor scraper is not yet implemented. Competitor data is not collected during refresh in v1. The schema and aggregation logic are present for future use.

**Rate limiting (eBay):** ~300 merchants x ~3 paginated requests each is ~900 calls per refresh. The per-day call budget depends on the API tier granted by eBay; this is pending approval (see §12 Q1). A 100ms sleep between calls is used as a starting point.

**Failure handling:** on per-merchant failure, log and skip. The merchant's most recent prior recommendation remains the latest known. The list view marks merchants whose latest recommendation is from a prior refresh — not a hard error, just a freshness indicator.

**Duplicate refresh defense:** the button is disabled in the UI while the in-flight run is being polled. As a defense, the server returns 409 if `POST /refresh` arrives during a running run.

---

## 6. Database schema

SQLite, single file at `data/zeal.db`. All timestamps are ISO 8601 UTC strings (SQLite's `datetime('now')` default).

### 6.1 Tables

**`merchants`** — per-merchant config, the heart of the system

```sql
CREATE TABLE merchants (
    merchant_id              TEXT PRIMARY KEY,
    display_name             TEXT NOT NULL,
    tier                     TEXT NOT NULL CHECK (tier IN ('T24','C','Z','NC')),
    in_store_margin          REAL NOT NULL,
    in_mail_margin           REAL NOT NULL,
    e_bonus                  REAL,
    ebay_differential        REAL NOT NULL,
    in_store_eligible        INTEGER NOT NULL CHECK (in_store_eligible IN (0,1)),
    in_mail_eligible         INTEGER NOT NULL CHECK (in_mail_eligible IN (0,1)),
    electronic_eligible      INTEGER NOT NULL CHECK (electronic_eligible IN (0,1)),
    online_sell_override     REAL,
    electronic_buy_override  REAL,
    merch_credit_variant     INTEGER NOT NULL CHECK (merch_credit_variant IN (0,1)),
    inclusion_regex          TEXT NOT NULL,
    exclusion_regex          TEXT,
    notes                    TEXT,
    is_active                INTEGER NOT NULL DEFAULT 1,
    ebay_weight              REAL NOT NULL DEFAULT 1.0 CHECK (ebay_weight >= 0.0 AND ebay_weight <= 1.0),
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`merchant_config_history`** — retained for direct-DB changes and the narrow v1 merchant config editor

```sql
CREATE TABLE merchant_config_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id  TEXT NOT NULL REFERENCES merchants(merchant_id),
    field_name   TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    reason       TEXT,
    changed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_config_history_merchant ON merchant_config_history(merchant_id, changed_at);
```

**`global_constants`** and **`global_constants_history`** — the `InputsandMargins` channel costs, bad-debt rates, and retained history

```sql
CREATE TABLE global_constants (
    key           TEXT PRIMARY KEY,
    value         REAL NOT NULL,
    description   TEXT,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE global_constants_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    key          TEXT NOT NULL,
    old_value    REAL,
    new_value    REAL NOT NULL,
    reason       TEXT,
    changed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`ebay_observations`** — raw sold-listing data, kept indefinitely

```sql
CREATE TABLE ebay_observations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id         TEXT NOT NULL REFERENCES merchants(merchant_id),
    listing_id          TEXT NOT NULL UNIQUE,
    sold_at             TEXT NOT NULL,
    face_value          REAL NOT NULL,
    sale_price          REAL NOT NULL,
    title               TEXT NOT NULL,
    raw_payload         TEXT,
    validity_status     TEXT NOT NULL DEFAULT 'valid' CHECK (validity_status IN ('valid','excluded','suspicious')),
    exclusion_reason    TEXT,
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_obs_merchant_date ON ebay_observations(merchant_id, sold_at DESC);
CREATE INDEX idx_obs_validity ON ebay_observations(merchant_id, validity_status);
```

**`ebay_summary`** — computed eBay sell %, one row per merchant per refresh day

```sql
CREATE TABLE ebay_summary (
    merchant_id              TEXT NOT NULL REFERENCES merchants(merchant_id),
    summary_date             TEXT NOT NULL,
    ebay_sell_pct            REAL,
    sample_size              INTEGER NOT NULL,
    most_recent_observation  TEXT,
    confidence               TEXT NOT NULL CHECK (confidence IN ('high','medium','low','none')),
    PRIMARY KEY (merchant_id, summary_date)
);
```

**`competitor_sources`** — one row per configured competitor source

```sql
CREATE TABLE competitor_sources (
    source_name             TEXT PRIMARY KEY,
    is_active               INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    collection_method       TEXT NOT NULL CHECK (collection_method IN ('scraper')),
    refresh_interval_days   INTEGER NOT NULL DEFAULT 7,
    last_successful_refresh TEXT,
    last_attempted_refresh  TEXT,
    notes                   TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`competitor_observations`** — raw and parsed competitor data, reference-only in v1

```sql
CREATE TABLE competitor_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name    TEXT NOT NULL REFERENCES competitor_sources(source_name),
    merchant_id    TEXT NOT NULL REFERENCES merchants(merchant_id),
    channel        TEXT NOT NULL CHECK (channel IN ('buy_mail','buy_electronic','sell','marketplace_sell')),
    price_pct      REAL,
    availability   TEXT NOT NULL CHECK (availability IN ('available','unavailable','no_data')),
    confidence     TEXT NOT NULL CHECK (confidence IN ('high','medium','low','none')),
    observed_at    TEXT NOT NULL,
    source_url     TEXT,
    raw_payload    TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_comp_obs_lookup ON competitor_observations(source_name, merchant_id, channel, observed_at DESC);
```

**`price_recommendations`** — append-only system of record for algorithm output

```sql
CREATE TABLE price_recommendations (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id            TEXT NOT NULL REFERENCES merchants(merchant_id),
    refresh_run_id         INTEGER NOT NULL REFERENCES refresh_runs(id),
    online_sell            REAL,
    in_mail_buy            REAL,
    in_store_buy           REAL,
    electronic_buy         REAL,
    ebay_sell_pct          REAL,
    ebay_confidence        TEXT NOT NULL CHECK (ebay_confidence IN ('high','medium','low','none')),
    no_data                INTEGER NOT NULL DEFAULT 0 CHECK (no_data IN (0,1)),
    formula_breakdown_json TEXT NOT NULL,
    config_snapshot_json   TEXT NOT NULL,
    computed_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_price_rec_merchant_time ON price_recommendations(merchant_id, computed_at DESC);
CREATE INDEX idx_price_rec_run ON price_recommendations(refresh_run_id);
```

**`refresh_runs`** — one row per on-demand refresh attempt

```sql
CREATE TABLE refresh_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    status         TEXT NOT NULL CHECK (status IN ('running','completed','partial','failed')),
    started_at     TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at   TEXT,
    processed      INTEGER NOT NULL DEFAULT 0,
    total          INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);
```

### 6.2 Schema design notes

- **Percentages are stored as fractions in [0, 1].** No `"78%"` strings, no integer percentages-times-100. The algorithm operates in fractions; UI converts on display.
- **Eligibility is per-channel.** The `in_store_eligible`, `in_mail_eligible`, `electronic_eligible` flags map directly to the spreadsheet's `"No"` convention. Any combination is permitted.
- **Override fields are surgical.** `online_sell_override` and `electronic_buy_override` exist for specific spreadsheet/config patterns where the standard formula does not apply. When `NULL`, the standard formula path runs.
- **`ebay_weight` stays in schema.** It defaults to 1.0 and v1 provides no UI to change it. Keeping the column avoids churn and preserves the v2 blending path.
- **No FK cascades on delete.** Merchants are never deleted, only deactivated (`is_active = 0`). This preserves history.
- **Snapshot config in `price_recommendations`.** When an old recommendation is reviewed months later, we want to know what the config was at the time, not what it is now. The JSON snapshot is the cheapest way to get this.
- **`price_recommendations` is append-only.** Every refresh writes new rows. The merchant detail page reads the historical trail. There is no `current_recommendation` table; "current" means "most recent row by `computed_at` for this merchant."
- **`competitor_observations` is append-only.** Every scraper run appends rows; existing observations are never modified or deleted. The table is the system of record for competitor pricing history. Queries for the current rate use `ORDER BY observed_at DESC LIMIT 1` scoped to merchant/channel.
- **No `published_prices` or `operator_actions` tables.** v1 does not track which recommendations the operator chose to apply. The merchant config editor changes formula inputs and writes config history; it is not operator action tracking. v2 may reintroduce published-price workflow once the operator's workflow is stable enough to define what "published" means in this tool's context.
- **No dedicated `users` table.** Single user, no auth needed.
- **Competitor data is reference-only in v1.** Competitor observations exist for operator context and future blending. They are not used by v1 recommendations.
- **Per-source schema, not per-merchant-per-source schema.** `competitor_observations` stores one row per observation, indexed by merchant, source, and time. Cross-source aggregation (per spec §7.4) happens at query time, not at storage time.

---

## 7. Dashboard — screens and flows

Two screens. Mobile-unfriendly is fine (operator works at a desktop).

### 7.1 Pricing list (home page, GET /)

A scrollable spreadsheet-style table of all active merchants, one row each. Columns:

- Merchant name (links to detail)
- Tier
- eBay sell %
- Online sell %
- In-mail buy %
- In-store buy %
- Electronic buy %
- Delta last run (signed; the channel that moved most, with channel label)
- Max absolute delta over last N (default N=5; signed; channel that moved most over the window)
- eBay confidence badge (high / medium / low / none)
- Last refresh timestamp

Default sort is `delta-from-last-run` descending by absolute value, so the largest movers are at the top. All columns are sortable by click. A merchant whose latest recommendation is from a prior refresh gets a "stale" indicator in the freshness column.

Header controls:
- "Refresh now" button. While a refresh is in progress, the button is replaced with a progress bar showing `{processed} / {total}` and the elapsed time. The progress bar updates via HTMX polling of `GET /refresh/status` every 2 seconds.
- A "last completed refresh" timestamp is always visible.

The visual density target is the spreadsheet's: tight rows, dominant data, minimal chrome. Padding is small; row height is the eye-comfortable minimum; merchant name is a regular link.

### 7.2 Merchant detail (GET /merchant/{merchant_id})

Single-merchant view, accessed by clicking a row in the list. Sections, top to bottom:

- **Latest recommendation** — the four channel prices, large and clear. eBay confidence badge.
- **Price history chart** — server-rendered line chart from saved `price_recommendations` rows for this merchant. Default visible lines are Online sell, In-mail buy, and eBay sell; in-store and electronic buy are also shown when enough values exist. The chart is recommendation history only and does not represent prices Zeal actually used, accepted, published, or applied outside the tool. Competitor chart lines are future/reference-only work; v1 keeps competitor data in the separate reference panel.
- **Formula breakdown** — per-channel worked formula from `BreakdownStep` sequences (spec §5.6). Rendered as a stack of `[label] [sign] [value]` rows leading to the final value.
- **Recent eBay observations** — table of the most recent 30 valid listings used in the average. Sortable by sold date, face value, sale price, computed sell percentage.
- **Excluded eBay observations** — collapsible table of listings filtered out, with `exclusion_reason`. Useful for debugging the regex and validity rules.
- **Competitor reference panel** — for each configured competitor source (v1: CardCash only), the most recent observation per channel: `price_pct`, `availability`, `confidence`, `observed_at`, source URL. Reference-only — explicitly marked as not feeding the recommendation in v1.
- **Recommendation history** — audit table of saved recommendation rows below the chart.
- **Recent refresh status for this merchant** — last 10 refreshes, success/skip/error.

v1 includes a narrow merchant config editor for one merchant at a time. It edits formula/config inputs such as margins, eligibility, regexes, and config override fields, and writes `merchant_config_history`. It does not edit published prices, accept recommendations, or record operator decisions.

---

## 8. Pricing engine — implementation outline

The algorithm is in `src/zeal/pricing/engine.py`. Pure functions, no side effects, no I/O. Blending logic lives in `pricing/blending.py`; competitor aggregation in `pricing/competitor_aggregate.py`.

All types use Pydantic `BaseModel` (not `@dataclass`). Key types in `src/zeal/models/` and their actual fields:

```python
# src/zeal/models/merchant.py
class MerchantConfig(BaseModel):
    merchant_id: str
    display_name: str
    tier: Literal["T24", "C", "Z", "NC"]
    in_store_margin: float
    in_mail_margin: float
    ebay_differential: float
    in_store_eligible: bool
    in_mail_eligible: bool
    electronic_eligible: bool
    merch_credit_variant: bool
    e_bonus: float | None = None
    online_sell_override: float | None = None
    electronic_buy_override: float | None = None
    ebay_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str | None = None

# src/zeal/models/pricing.py
class GlobalConstants(BaseModel):
    ebay_sale_costs: float
    paypal_sell_costs: float
    ebay_postage_costs: float
    online_store_postage_costs: float
    online_sell_bonus_competitive: float
    online_sell_bonus_zen_nocomp: float
    in_store_bad_debt: float
    in_mail_bad_debt: float
    online_bad_debt: float
    competitor_electronic_markdown: float = 0.05

class CompetitorAggregate(BaseModel):
    online_sell: float | None = None
    in_mail_buy: float | None = None
    electronic_buy: float | None = None
    sources_contributing: Sequence[str] = ()

class BreakdownStep(BaseModel):
    label: str
    value: float | str
    sign: Literal["+", "-", "=", "*", "blend"]

class ChannelResult(BaseModel):
    final_value: float | Literal["No", "No Data"]
    ebay_only_value: float | Literal["No", "No Data"]
    competitor_only_value: float | None = None
    breakdown: Sequence[BreakdownStep] = Field(default_factory=tuple)

class PriceRecommendation(BaseModel):
    online_sell: ChannelResult
    in_mail_buy: ChannelResult
    in_store_buy: ChannelResult
    electronic_buy: ChannelResult
    no_data: bool
    confidence: Literal["high", "medium", "low", "none"]
```

The `compute_prices()` signature:

```python
def compute_prices(
    ebay_sell_pct: float | None,
    ebay_confidence: Literal["high", "medium", "low", "none"],
    competitor: CompetitorAggregate,
    config: MerchantConfig,
    constants: GlobalConstants,
) -> PriceRecommendation: ...
```

The body implements `pricing_algorithm.md` §5; the spec is the source of truth. Do not duplicate the formula logic here.

In v1 the dashboard always passes `config.ebay_weight = 1.0`, so the recommendation equals the eBay-only path output regardless of `competitor` content. The engine still computes and returns competitor-only and blended values internally; they are unit-tested but not surfaced to the operator. v2 introduces UI to vary `ebay_weight` per merchant.

**Test strategy:** the file `tests/fixtures/spreadsheet_baseline.json` verifies the faithful-port property (281 records, `ebay_weight = 1.0`). The 493-test suite covers engine paths, confidence, listing filter, blending, repositories, routes, and CLI. Golden tests assert outputs match to within +/-0.001.

---

## 9. Windows deployment

### 9.1 First-time setup on the operator's machine

One-time, ~20 minutes:

1. Install **Python 3.12 from python.org** (`winget install Python.Python.3.12` or
   download from python.org/downloads). Check "Add to PATH" if using the GUI installer.
   Do NOT use a uv-managed python-build-standalone interpreter — it omits the OpenSSL
   applink shim required for correct TLS on Windows, causing `CERTIFICATE_VERIFY_FAILED`
   on sites like cardcash.com and api.ebay.com.
2. Install `uv`: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. Install Git for Windows.
4. Clone the repo to `C:\zeal-pricing-tool`.
5. `uv sync` — installs dependencies (including `truststore` for Windows TLS).
   Run in **PowerShell**, not Git Bash: Git Bash resolves `python.exe` from
   `mingw64\bin` before the system PATH, which can silently pick the wrong interpreter
   and break SSL DLL resolution.
6. Create `.env` from `.env.example`. Leave `ZEAL_EBAY_MODE=synthetic` until production Marketplace Insights access is confirmed.
7. `uv run zeal init-db` — creates the SQLite file at `data/zeal.db`.
8. `uv run zeal seed` — loads merchant data from the baseline fixture.
9. `uv run zeal serve` — starts the dashboard at `http://127.0.0.1:8000`.

### 9.2 Daily use

- Run `uv run python -m zeal.cli serve` in a terminal window (keep it open while using the dashboard).
- Open `http://127.0.0.1:8000` in a browser.
- Operator clicks "Refresh now" when he wants new pricing data (live mode only), watches the progress bar, then reviews the saved recommendations.
- When done, close the terminal window.

### 9.3 Updates

When new code lands on `main`:

1. Operator (or developer) runs `git pull` in the repo directory.
2. Run `uv sync` if dependencies changed.
3. If the schema changed, apply the migration SQL manually or re-seed into a fresh DB.
4. Restart the dashboard.

Manual process. Acceptable for one user.

---

## 10. Backup and recovery

**What to back up:** `data/zeal.db` is the only stateful file. Everything else is in git. The database includes merchant config, all eBay observations, all competitor observations, all recommendation history, and refresh logs.

**v1 approach:** the operator manually copies `data/zeal.db` to OneDrive (or another location) when he wants a backup. We document the copy command in the README.

**Why no automated backup script:** automated nightly backup was on the v1 list initially but was tied to the scheduled-refresh framing; with on-demand refresh the operator may go days without running the tool, making "nightly" meaningless. A manual copy is one PowerShell command and works on the operator's actual cadence. v2 may add an in-app "back up now" button if it becomes a recurring ask.

**Recovery from total loss:**
- Reinstall on the same or a new machine via §9.1 steps 1-6.
- Replace the empty `data/zeal.db` with a backup copy.
- Done.

---

## 11. Build sequence

Three stepping-stone versions after Phase 1, each producing something demoable. The principle is **smallest end-to-end slice working before going wide**, with each stone narrower in scope than the prior architecture's phase.

### Phase 1 — Foundation — COMPLETE

Pure-function pricing engine, Pydantic models, SQLite schema, spreadsheet parser, golden test against 281 baseline merchants. All tests passing at +/-0.001 tolerance. See repo `main` branch (PR #2, merged).

### Phases 1–3 — COMPLETE

- Phase 1: pure-function pricing engine, Pydantic models, SQLite schema, spreadsheet parser, 281-record golden baseline tests.
- Phase 2: FastAPI dashboard skeleton, pricing list + merchant detail views, synthetic seeder, on-demand refresh button, config editor.
- Phase 3: live eBay Marketplace Insights client, OAuth flow, listing filter, refresh orchestrator, smoke-ebay CLI, HTMX progress bar. Live eBay refresh is gated on production Marketplace Insights entitlement (currently blocked — see §12 Q1).

Current state: all of the above is implemented and tested. The tool operates in synthetic mode (seeded spreadsheet-baseline recommendations). Dashboard includes pricing list, merchant detail (recommendation cards, price history chart, formula breakdown, eBay observations, competitor reference panel), narrow config editor, and source/confidence badges.

### Phase 4 — CardCash competitor scraper — COMPLETE

Goal: automated competitor data collection.

As built:
- `src/zeal/ingestion/competitor/cardcash.py` — `CardCashClient`: buy-blob parser
  (sell channel), sell-cart flow (buy channel), session resilience, canary checks.
- `src/zeal/ingestion/competitor/refresh.py` — `run_competitor_refresh()` orchestrator
  with `CompetitorRefreshSummary`; `zeal refresh-competitors --limit N` CLI.
- 184 merchants mapped via operator-reviewed CSV (`data/cardcash_mapping_approved.csv`).
- Full 184-merchant live run completed 2026-06-24: `status=completed`, no 429 at 750ms
  cadence. Harvest: 155 sell available / 29 unavailable; 122 buy_electronic + 23 buy_mail
  available; 39 no_data (buy-only merchants returning 400 on card-add — correct behavior).
- Rates verified accurate against live cardcash.com (AMC sell 0.925 ↔ "7.5% off";
  Abercrombie buy 0.805 ↔ "$80.50 on $100"). Both conversion formulas confirmed
  end-to-end in production.
- Competitor reference panel renders live rates on merchant detail pages.
- Competitor data remains reference-only; never feeds `compute_prices()`; golden baseline
  and `ebay_weight=1.0` invariant untouched throughout.
- 75 tests across scraper, mapping, and orchestrator modules.

Open item: `landry_s` (Landry's) and `ann_taylor_loft` (Ann Taylor / Loft) left unmapped
pending operator confirmation of what Zeal trades there.

### Phase 5 — Polish and stabilize

Competitor reference panel now renders live CardCash rates, completing the original
Phase 4 acceptance criterion. Ongoing: bug fixes from operator feedback, UI tweaks,
edge case handling as the tool is used in real workflow.

After Phase 5: stabilize. v2 (per `pricing_algorithm.md` §11) starts only after the
operator has used v1 long enough to have informed feedback on which v2 improvements are
worth the effort.

### Next phase — eBay sold-listings scraper

Replaces the blocked eBay Marketplace Insights API path with DIY httpx scraping of
eBay sold/completed listings, behind the existing `EbayClient` protocol seam
(`src/zeal/ingestion/ebay_client.py`). The scraper adapter slots in alongside
`SyntheticEbayClient`; `filter_listings()` and `compute_ebay_average()` are unchanged.
See `docs/ebay_scraper_handoff.md` for the fresh-session starting brief.

---

## 12. Open questions

Tracked here so the build does not get blocked on missing answers, but listed so we can resolve them as we go:

- **Q1.** eBay API access status. As of 2026-05-10: production Marketplace Insights API access is NOT yet granted. The sandbox keyset has the `buy.marketplace.insights` scope; the production keyset does not. Awaiting eBay support. v1 currently operates in synthetic mode. Sold-listing data requires the **Marketplace Insights API** — Browse API provides active listings only and is not a valid source for the eBay sell % computation. See decisions_log.md 2026-05-05 and 2026-05-10 for fallback and waiting-state decisions.
- **Q2.** ~~Display: percentages or dollar amounts?~~ **Resolved:** operator confirmed percentages. See decisions_log.md 2026-05-03.
- **Q3.** Currency formatting (78.5% vs 0.785 vs $78.50/$100). Use percentages with one decimal place, matching the spreadsheet's convention.
- **Q4.** When the operator updates `online_sell_override` for a Pattern A merchant, should the on-demand refresh skip eBay ingestion entirely for that merchant? Default: yes — no eBay calls for merchants with the override set. Saves rate-limit budget and avoids generating misleading "No Data" warnings.
- **Q5.** What is the right `competitor_electronic_markdown` value? 0.05 is provisional and v2-relevant; it only matters when competitor-aware recommendations are surfaced.
- **Q6.** CardCash request rate: starting at 500-1000ms per request. Adjust based on observed CardCash response.

---

## 13. Out of scope (explicit)

To keep v1 scoped:

- No website integration (architectural feasibility preserved; not a v1 feature).
- No multi-user accounts or auth (single-user assumption).
- No mobile UI.
- No automated price publishing.
- No scheduled refresh — refresh is on-demand only.
- No operator action workflow (accept/override/skip).
- No `published_prices` or `operator_actions` tables.
- No risk/watchlist flagging.
- No CSV export.
- No global constants editor or bulk merchant config editor.
- Narrow one-merchant-at-a-time merchant config editing is in v1 scope for formula/config inputs only; it is not operator action tracking.
- No `ebay_weight` UI — field exists in schema and engine, locked at 1.0 in v1.
- No internal sale history integration.
- No automated bankruptcy or risk monitoring.
- No recency-weighted or outlier-filtered eBay averaging beyond range checks and keyword exclusions.
- No dynamic tier reassignment.
- No email/SMS alerts on failures (logs only).
- No internationalization.
- No automated competitor source discovery.
- Only one competitor source in v1 (CardCash). Additional sources are v2. When a second source is added, evaluate whether to normalize source-specific merchant identifiers into a `competitor_merchant_mapping(merchant_id, source_name, source_key)` table (replacing the per-column approach of `merchants.cardcash_id`) — see `pricing_algorithm.md §11` item 17 and `competitor_scraper_design.md §5`.
- No automated database backup — manual copy as documented in §10.

All of these are tracked in the algorithm spec's v2 roadmap or are de novo improvements for later versions.

---

## 14. Acceptance criteria for the build

The v1 architecture (phases 1–3) is correctly implemented when:

1. All algorithm spec acceptance criteria are met (per `pricing_algorithm.md` §13).
2. `uv run python -m zeal.cli serve` launches and renders the pricing list view of all active merchants.
3. The merchant detail page renders recommendation cards, price history chart, formula breakdown, eBay observations (or synthetic empty state), competitor reference panel, and recommendation history for every merchant.
4. The "Refresh now" button (live mode only) completes a full refresh of all active merchants without manual intervention beyond the click. Progress bar updates as merchants are processed. (Gated on production Marketplace Insights entitlement — see §12 Q1.)
5. The operator can complete a full review (scan list, drill into outliers, return to list) in under 30 minutes for the typical case.
6. The repo passes `uv run ruff check .` and `uv run pytest` cleanly.
7. The pure-function boundary in `pricing/` is preserved: no FastAPI, SQLite, or httpx imports anywhere in `src/zeal/pricing/`. Verified by `rg "fastapi|sqlite3|httpx" src/zeal/pricing/`.
8. Documentation in `docs/` reflects the as-built system.

Criteria for Phase 4 (CardCash scraper) are tracked separately and apply after the scraper is built.
