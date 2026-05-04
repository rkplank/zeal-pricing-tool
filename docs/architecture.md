# Zeal Pricing Tool — Architecture

**Status:** Draft for review — v1 scope expanded 2026-05-04
**Companion to:** `pricing_algorithm.md`
**Last updated:** 2026-05-04

This document specifies how the v1 pricing tool is built and deployed. It assumes the algorithm spec is the source of truth for *what* the system computes; this doc covers *how*.

---

## 1. Goals and non-goals

**Goals:**
- A working pricing dashboard the operator can use daily within ~4 weeks of starting the build
- Faithful implementation of the algorithm spec
- Easy for one developer to maintain (no exotic dependencies, no surprise complexity)
- Forward-compatible — if the tool eventually moves to powering the Zeal Cards website, the path is straightforward

**Non-goals:**
- Multi-user support
- Real-time pricing (daily is enough)
- Hosted/SaaS deployment
- Mobile app or responsive design beyond "looks fine on a laptop"
- Automated price publishing
- Automated competitor source discovery (CardCash and Raise are configured manually; new sources added by operator+developer collaboration, not auto-detection)

---

## 2. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | Best ecosystem for HTTP scraping, data handling, eBay API |
| Web framework | FastAPI | Modern, async-capable, well-documented, plays nicely with HTMX |
| Templating | Jinja2 | Standard for FastAPI server-rendered pages |
| Frontend | HTMX + Tailwind | Server-rendered HTML with minimal JS; right complexity for a one-user dashboard |
| Database | SQLite | Single file, zero config, plenty for one user × ~300 merchants |
| HTTP client | httpx | Async, modern, replaces requests |
| HTML parsing | selectolax or BeautifulSoup4 | For competitor source scraping. selectolax preferred (faster, lower memory). |
| Validation | Pydantic v2 | Built into FastAPI; defines all data shapes |
| Env management | uv | Fastest tool, single binary, replaces pip/venv/poetry |
| Testing | pytest + pytest-asyncio | Standard |
| Linting/formatting | ruff | Replaces black, isort, flake8 in one tool |
| Process supervision | None initially — see §9 | Simple desktop shortcut sufficient |
| Scheduling | Windows Task Scheduler | Built into the OS, no extra dependency |

Versions are floors, not ceilings. We pin in `pyproject.toml`.

---

## 3. Repository layout

```
zeal-pricing-tool/
├── README.md
├── pyproject.toml              # uv-managed, all deps declared
├── .python-version             # 3.12
├── .env.example                # Template for local secrets (eBay API keys etc.)
├── .gitignore                  # data/, .env, __pycache__, etc.
├── docs/
│   ├── pricing_algorithm.md
│   ├── architecture.md         # this file
│   └── decisions_log.md
├── src/zeal/
│   ├── __init__.py
│   ├── config.py               # env vars, paths, constants loader
│   ├── cli.py                  # `zeal serve`, `zeal refresh`, `zeal seed`
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql          # canonical schema
│   │   ├── connection.py       # connection pool, transactions
│   │   └── migrations/         # numbered SQL files
│   ├── models/                 # Pydantic models for all data shapes
│   │   ├── merchant.py
│   │   ├── pricing.py
│   │   └── ebay.py
│   ├── ingestion/
│   │   ├── ebay_client.py      # eBay Browse API wrapper
│   │   ├── refresh.py          # daily refresh orchestrator
│   │   └── competitor/         # competitor source ingestion
│   │       ├── __init__.py
│   │       ├── base.py         # CompetitorSource protocol
│   │       ├── cardcash.py     # CardCash scraper (v1 first source)
│   │       ├── raise_.py       # Raise scraper (Phase 5)
│   │       ├── manual.py       # Manual entry / CSV import path
│   │       └── refresh.py      # Per-source competitor refresh orchestrator
│   ├── pricing/
│   │   ├── ebay_average.py     # volume-weighted average from spec §6.3
│   │   ├── listing_filter.py   # validity rules from spec §6.2
│   │   ├── competitor_aggregate.py  # per-source and cross-source aggregation per spec §7
│   │   ├── confidence.py       # confidence scoring from spec §6.4 and §7.5
│   │   ├── blending.py         # eBay/competitor blending per spec §5
│   │   └── engine.py           # the four channel formulas from spec §5
│   ├── web/
│   │   ├── app.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── dashboard.py    # main views
│   │   │   ├── merchants.py    # config editor
│   │   │   ├── actions.py      # accept/override/skip
│   │   │   ├── admin.py        # global constants, manual refresh
│   │   │   ├── competitor.py   # competitor data import / view routes
│   │   │   └── export.py       # CSV export route
│   │   ├── templates/          # Jinja2 + HTMX
│   │   │   ├── base.html
│   │   │   ├── dashboard.html
│   │   │   └── partials/
│   │   │       ├── breakdown.html        # formula breakdown rendering
│   │   │       ├── risk_badge.html       # risk_status display
│   │   │       └── competitor_panel.html # competitor data on merchant detail
│   │   └── static/
│   │       ├── style.css       # Tailwind output
│   │       └── htmx.min.js
│   └── jobs/
│       └── daily_refresh.py    # entry point for Task Scheduler
├── tests/
│   ├── conftest.py
│   ├── test_pricing_engine.py
│   ├── test_ebay_average.py
│   ├── test_confidence.py
│   ├── test_listing_filter.py
│   └── fixtures/
│       ├── spreadsheet_baseline.json   # faithful-port golden records (281 merchants)
│       ├── blending_cases.json         # blending math at ebay_weight ∈ {0.5, 0.7, 0.9}
│       └── exclusion_cases.json        # extended validity filter behavior
├── scripts/
│   ├── seed_from_spreadsheet.py        # one-time merchant import
│   ├── backup_db.ps1                   # PowerShell, copies SQLite to OneDrive
│   ├── install_scheduled_task.ps1      # registers Windows scheduled task
│   └── launch_dashboard.ps1            # double-clickable launcher
└── data/
    └── .gitkeep                # SQLite file lives here; contents gitignored
```

The split between `ingestion`, `pricing`, and `web` matters: the algorithm code (`pricing/`) has zero dependencies on web framework or database, which means it's trivially testable and could be reused in another context without rework. `listing_filter.py` and `blending.py` live in `pricing/` (not `ingestion/`) because they are pure functions with no I/O.

---

## 4. Component map

Seven components, with explicit dependencies:

```
┌─────────────────────────────────────────────────────────┐
│                     Windows Task Scheduler              │
│                  (fires daily-refresh.py at 6 AM)       │
└────────────────────────┬────────────────────────────────┘
                         ▼
       ┌──────────────────────────────────┐
       │  Daily Refresh Orchestrator       │
       │  (ingestion/refresh.py)           │
       └──────┬─────────────────────┬──────┘
              ▼                     ▼
   ┌──────────────────┐   ┌──────────────────┐
   │  eBay Ingestion   │   │  Pricing Engine   │
   │  (ingestion/)     │──▶│  (pricing/)       │
   └────────┬──────────┘   └─────────┬─────────┘
            │                        │
   ┌──────────────────┐              │
   │ Competitor        │              │
   │ Ingestion         │──────────────┤
   │ (ingestion/       │              │
   │  competitor/)     │              │
   └────────┬──────────┘              │
            ▼                        ▼
       ┌────────────────────────────────┐
       │         SQLite Database         │
       │            (db/)                │
       └─────────────────┬──────────────┘
                         ▲
                         │
       ┌─────────────────┴──────────────┐
       │       Dashboard (FastAPI)       │
       │            (web/)               │
       └─────────────────┬──────────────┘
                         ▲
                         │
       ┌─────────────────┴──────────────┐
       │     Operator browser            │
       │       (localhost:8000)          │
       └────────────────────────────────┘
```

**Component responsibilities:**

1. **eBay Ingestion** — Calls eBay Browse API, paginates, filters listings per spec §6.2, writes raw observations to `ebay_observations` with `validity_status` and `exclusion_reason`. Idempotent; safe to re-run. Talks only to eBay and the database.

2. **Competitor Ingestion** — One module per source, all conforming to a `CompetitorSource` protocol. CardCash scrapes HTML on weekly cadence. Manual import accepts CSV uploads. Raise integrates after CardCash has been operationally validated. Each source writes to `competitor_observations` with confidence and availability flags. Talks only to its source and the database.

3. **Pricing Engine** — Pure functions (no I/O). Reads merchant config, eBay observations, and competitor aggregates from arguments; returns `PriceRecommendation` objects with per-channel breakdowns. The formulas from spec §5 live here. Heavily tested.

4. **Daily Refresh Orchestrator** — The conductor for eBay data. For each active merchant: trigger eBay ingestion, compute the eBay average, run the pricing engine (which reads competitor aggregates from the database), write recommendations. Logs results to `refresh_runs` table.

5. **Database** — SQLite at `data/zeal.db`. Schema in §6. Migrations are numbered SQL files applied at startup.

6. **Dashboard (FastAPI)** — The operator UI. Read-heavy; the only writes are operator actions (accept/override/skip), config edits, and manual competitor data entries.

7. **Scheduler** — Windows Task Scheduler entries that run `python -m zeal.jobs.daily_refresh` (eBay, daily at 6 AM) and each competitor source on its own cadence. No code in our repo; just registration scripts.

---

## 5. Daily refresh — data flow

What happens at 6 AM:

1. Task Scheduler fires `python -m zeal.jobs.daily_refresh`
2. The job creates a row in `refresh_runs` with status `running`
3. For each `is_active = 1` merchant:
   - Query eBay Browse API for sold listings matching the merchant's regex, last 90 days, US only
   - For each listing returned: apply validity filters (spec §6.2), upsert into `ebay_observations` (deduped by `listing_id`), recording `validity_status` and `exclusion_reason`
   - Compute `ebay_sell_pct` per spec §6.3 (volume-weighted avg of last 10 valid)
   - Compute eBay confidence per spec §6.4
   - Upsert one row in `ebay_summary` for today
   - Load merchant config; read competitor aggregates from `competitor_observations` per spec §7.3–§7.4
   - Run pricing engine → four channel prices with breakdowns
   - Insert into `price_recommendations`
4. Mark `refresh_runs` row `completed`, with counts
5. If anything fails: mark `failed`, write error to log, continue with next merchant (one bad merchant doesn't break the run)

**Competitor refresh cadence.** Each competitor source has its own scheduled refresh, default weekly. Sources are configured via the `competitor_sources` table. The competitor refresh orchestrator is a parallel job to the eBay daily refresh; both write to the database and can run concurrently. Cross-source aggregation (per spec §7.4) happens at recommendation time, reading whatever observations are currently in the database, so per-source refresh timing doesn't need coordination.

**Rate limiting:** eBay Browse API allows 5,000 calls/day on free tier. ~300 merchants × ~3 paginated requests each = ~900 calls. Well under limit. We add a 100ms sleep between calls to be polite. Competitor scrapers add a 500–1000ms sleep between requests, longer than eBay's 100ms because competitor sources are not designed for bulk programmatic access and we want to be visibly polite. CardCash specifically should be tested at this cadence and adjusted if the source rate-limits us.

**Failure handling:** On API failure for a merchant, log the error and skip — the merchant's previous-day data remains the latest known. Dashboard shows "stale" badge if data is more than 36 hours old.

**Manual refresh:** The dashboard has an admin-only "Refresh now" button that runs the same job in-process. Useful for testing and for when the scheduled run fails overnight.

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
    e_bonus                  REAL,                          -- NULL if no electronic computation needed
    ebay_differential        REAL NOT NULL,
    in_store_eligible        INTEGER NOT NULL CHECK (in_store_eligible IN (0,1)),
    in_mail_eligible         INTEGER NOT NULL CHECK (in_mail_eligible IN (0,1)),
    electronic_eligible      INTEGER NOT NULL CHECK (electronic_eligible IN (0,1)),
    online_sell_override     REAL,                          -- NULL for normal merchants; set for "Pattern A" (~25 NC merchants)
    electronic_buy_override  REAL,                          -- NULL for normal merchants; set for Home Depot eStore Credit only
    merch_credit_variant     INTEGER NOT NULL CHECK (merch_credit_variant IN (0,1)),
    inclusion_regex          TEXT NOT NULL,                 -- for matching eBay listing titles
    exclusion_regex          TEXT,                          -- e.g. exclude 'Michaels' when matching 'Michael Kors'
    notes                    TEXT,
    is_active                INTEGER NOT NULL DEFAULT 1,
    -- v1 expansion fields:
    ebay_weight              REAL NOT NULL DEFAULT 1.0 CHECK (ebay_weight >= 0.0 AND ebay_weight <= 1.0),
    risk_status              TEXT NOT NULL DEFAULT 'normal' CHECK (risk_status IN ('normal','watch','paused','no_buy')),
    risk_note                TEXT,
    -- audit:
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`merchant_config_history`** — every change to a merchant's config, for the operator-overrides-as-training-data goal

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

**`global_constants`** — the `InputsandMargins` channel costs and bad-debt rates

```sql
CREATE TABLE global_constants (
    key           TEXT PRIMARY KEY,    -- e.g. 'ebay_sale_costs'
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
    listing_id          TEXT NOT NULL UNIQUE,                   -- eBay's item id
    sold_at             TEXT NOT NULL,                          -- when the eBay sale closed
    face_value          REAL NOT NULL,
    sale_price          REAL NOT NULL,                          -- includes shipping
    title               TEXT NOT NULL,                          -- raw, for debugging
    raw_payload         TEXT,                                   -- JSON of full eBay item
    -- v1 expansion fields:
    validity_status     TEXT NOT NULL DEFAULT 'valid' CHECK (validity_status IN ('valid','excluded','suspicious')),
    exclusion_reason    TEXT,                                   -- populated when validity_status = 'excluded'
    -- audit:
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_obs_merchant_date ON ebay_observations(merchant_id, sold_at DESC);
CREATE INDEX idx_obs_validity ON ebay_observations(merchant_id, validity_status);
```

The `'suspicious'` value in `validity_status` is reserved for v1.1; v1 application code does not produce or consume it. Including it in the CHECK constraint avoids a schema migration when v1.1 lands.

**`ebay_summary`** — daily computed eBay sell %, one row per merchant per day

```sql
CREATE TABLE ebay_summary (
    merchant_id              TEXT NOT NULL REFERENCES merchants(merchant_id),
    summary_date             TEXT NOT NULL,                                    -- 'YYYY-MM-DD'
    ebay_sell_pct            REAL,                                             -- NULL if no data
    sample_size              INTEGER NOT NULL,
    most_recent_observation  TEXT,                                             -- ISO date
    confidence               TEXT NOT NULL CHECK (confidence IN ('high','medium','low','none')),
    PRIMARY KEY (merchant_id, summary_date)
);
```

**`competitor_sources`** — one row per configured competitor source

```sql
CREATE TABLE competitor_sources (
    source_name             TEXT PRIMARY KEY,
    is_active               INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    collection_method       TEXT NOT NULL CHECK (collection_method IN ('scraper','manual','csv_import')),
    refresh_interval_days   INTEGER NOT NULL DEFAULT 7,
    last_successful_refresh TEXT,
    last_attempted_refresh  TEXT,
    notes                   TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**`competitor_observations`** — per-source buy/sell observations, kept indefinitely

```sql
CREATE TABLE competitor_observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id     TEXT NOT NULL REFERENCES merchants(merchant_id),
    source_name     TEXT NOT NULL REFERENCES competitor_sources(source_name),
    channel         TEXT NOT NULL CHECK (channel IN ('buy_mail','buy_electronic','sell','marketplace_sell')),
    price_pct       REAL NOT NULL,
    availability    TEXT NOT NULL CHECK (availability IN ('available','unavailable','no_data')),
    confidence      TEXT NOT NULL CHECK (confidence IN ('high','medium','low','none')),
    observed_at     TEXT NOT NULL,
    source_url      TEXT,
    raw_payload     TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_competitor_merchant ON competitor_observations(merchant_id, source_name, observed_at DESC);
CREATE INDEX idx_competitor_recent ON competitor_observations(observed_at DESC);
```

**`price_recommendations`** — algorithm output, one row per merchant per refresh, kept indefinitely for history

```sql
CREATE TABLE price_recommendations (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id                 TEXT NOT NULL REFERENCES merchants(merchant_id),
    computed_at                 TEXT NOT NULL DEFAULT (datetime('now')),
    online_sell                 REAL,
    in_mail_buy                 REAL,
    in_store_buy                REAL,
    electronic_buy              REAL,
    electronic_buy_sentinel     TEXT,                                          -- 'No' or NULL
    no_data                     INTEGER NOT NULL DEFAULT 0,
    confidence                  TEXT NOT NULL,
    ebay_sell_pct_used          REAL,
    snapshot_config_json        TEXT NOT NULL                                  -- JSON of merchant config at compute time, for audit
);
CREATE INDEX idx_recs_merchant_date ON price_recommendations(merchant_id, computed_at DESC);
```

**`published_prices`** — what the operator has approved as "current," one row per merchant

```sql
CREATE TABLE published_prices (
    merchant_id                  TEXT PRIMARY KEY REFERENCES merchants(merchant_id),
    online_sell                  REAL,
    in_mail_buy                  REAL,
    in_store_buy                 REAL,
    electronic_buy               REAL,
    electronic_buy_sentinel      TEXT,
    published_at                 TEXT NOT NULL,
    based_on_recommendation_id   INTEGER REFERENCES price_recommendations(id),
    operator_action              TEXT NOT NULL CHECK (operator_action IN ('accept','override','skip')),
    operator_note                TEXT
);
```

**`operator_actions`** — full log of every accept/override/skip, the future training data

```sql
CREATE TABLE operator_actions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id                 TEXT NOT NULL REFERENCES merchants(merchant_id),
    recommendation_id           INTEGER REFERENCES price_recommendations(id),
    action                      TEXT NOT NULL CHECK (action IN ('accept','override','skip')),
    override_online_sell        REAL,
    override_in_mail_buy        REAL,
    override_in_store_buy       REAL,
    override_electronic_buy     REAL,
    reason                      TEXT,
    actioned_at                 TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_actions_merchant ON operator_actions(merchant_id, actioned_at DESC);
```

**`refresh_runs`** — log of each daily eBay refresh, for ops visibility

```sql
CREATE TABLE refresh_runs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at             TEXT NOT NULL,
    completed_at           TEXT,
    status                 TEXT NOT NULL CHECK (status IN ('running','completed','failed','partial')),
    merchants_processed    INTEGER,
    merchants_with_data    INTEGER,
    error_summary          TEXT
);
```

### 6.2 Schema design notes

- **All percentages stored as floats in [0, 1].** No "78%" strings, no integer percentages-times-100. The algorithm operates in fractions; UI converts on display.
- **Eligibility is per-channel.** The `in_store_eligible`, `in_mail_eligible`, `electronic_eligible` flags map directly to the spreadsheet's `"No"` convention in columns C, E, D respectively. Any combination is permitted.
- **Override fields are surgical.** `online_sell_override` and `electronic_buy_override` exist for specific spreadsheet patterns where the standard formula doesn't apply. When `NULL`, the standard formula path runs.
- **No FK cascades on delete.** Merchants are never deleted, only deactivated (`is_active = 0`). This preserves history.
- **Snapshot config in `price_recommendations`.** When an old recommendation is reviewed months later, we want to know what the config *was at the time*, not what it is now. The JSON snapshot is the cheapest way to get this.
- **No dedicated `users` table.** Single user, no auth needed.
- **Competitor data is reference, not authoritative.** Competitor observations exist for blending and operator context. They are not used by the spreadsheet-faithful baseline and at `ebay_weight = 1.0` they are computed but not consumed.
- **Per-source schema, not per-merchant-per-source schema.** `competitor_observations` stores one row per observation, indexed by merchant, source, and time. Cross-source aggregation (per spec §7.4) happens at query time, not at storage time. This keeps writes simple and lets aggregation rules evolve without re-ingestion.

---

## 7. Dashboard — screens and flows

Seven screens. Mobile-unfriendly is fine (operator works at a desktop).

### 7.1 Daily Review (home page)

The screen the operator opens every morning. Three sections:

- **High priority** — merchants with delta >2pp from current published price, or confidence dropped to low/none, or no data, or `risk_status` is `paused` or `no_buy`
- **Medium priority** — delta 0.5–2pp, or `risk_status` is `watch`
- **Low priority** — collapsed by default

Each merchant row shows: display name, risk badge if not normal, current published prices, recommended prices, deltas, confidence badge, competitor-influence indicator (small icon when `ebay_weight < 1.0` and competitor data contributed), action buttons (Accept / Override / Skip).

Action buttons are HTMX-powered: clicking Accept fires a POST and the row updates in place. No page reload. For merchants with `risk_status` of `paused` or `no_buy`, the Accept button requires an explicit confirmation step before writing.

### 7.2 Merchant Detail

One merchant, all the context:

- Current published prices and their recommendation source
- Today's recommendation with structured formula breakdown (eBay path, competitor path, blending — per spec §5.6)
- eBay weight slider with current value (operator can adjust here or in config editor)
- Risk status badge and note (if not `normal`)
- eBay sell percentage used, sample size, confidence, freshness
- Recent eBay observations table (last 30 listings, sortable)
- Excluded eBay observations table (with `exclusion_reason` per spec §6.2) — collapsible, expanded on demand
- Competitor data panel — per-source observations, channel, price_pct, availability, confidence, observed_at, source URL link
- Price history chart (last 90 days, all four channels)
- Operator action history for this merchant
- Override interface

### 7.3 Config Editor

Per-merchant: edit margins, e-bonus, eBay differential, regexes, electronic-eligible flag, `ebay_weight`, `risk_status`, `risk_note`. Every save logs to `merchant_config_history` and prompts for an optional reason.

Bulk operations are out of scope for v1 (operator edits one at a time).

### 7.4 Global Constants

Single page listing the global constants with current value and edit button. Same logging pattern as merchant config.

### 7.5 Refresh Status

Last successful eBay refresh time, last failure if any, "Refresh now" button. Shows in-progress status when a refresh is running.

**Competitor sources panel:** for each row in `competitor_sources`, show: source name, last successful refresh (with staleness color: green ≤ refresh_interval_days, yellow up to 2×, red beyond), last attempted refresh, observation count in last 30 days. Manual "Refresh now" button per source.

### 7.6 Competitor Data Admin

A dedicated section for working with competitor data at the source level:

- **Source list** — same content as the Refresh Status panel, plus enable/disable toggle and refresh interval edit.
- **Manual entry form** — operator selects merchant, source, channel, enters price_pct and availability. Used for sources without a scraper, or to override a scraped value the operator has reason to distrust.
- **CSV import** — upload a CSV with columns matching `competitor_observations` schema. Used for backfilling historical data (deferred, but the surface exists) or bulk corrections.
- **Recent observations table** — last 100 observations across all sources, sortable, exportable for audit.
- **Per-source observation view** — drill into one source to see all its recent observations and parse-failure logs.

### 7.7 CSV Export

Approved/published prices export to UTF-8 CSV. Trigger via "Export CSV" button in the Daily Review header and in the admin section. Columns:

- `merchant_id`
- `display_name`
- `online_sell`
- `in_mail_buy`
- `in_store_buy`
- `electronic_buy`
- `published_at`
- `risk_status`

Empty/null prices render as blank cells. Filename: `zeal_prices_YYYY-MM-DD.csv`.

The export is read-only; clicking the button does not modify any prices or state. §13 explicitly rules out automated price publishing.

---

## 8. Pricing engine — implementation outline

The algorithm is in `src/zeal/pricing/engine.py`. Pure functions, no side effects, no I/O. Blending logic lives in `pricing/blending.py`; competitor aggregation in `pricing/competitor_aggregate.py`.

```python
from dataclasses import dataclass
from typing import Literal, Sequence

@dataclass(frozen=True)
class MerchantConfig:
    in_store_margin: float
    in_mail_margin: float
    e_bonus: float | None
    ebay_differential: float
    in_store_eligible: bool
    in_mail_eligible: bool
    electronic_eligible: bool
    online_sell_override: float | None = None
    electronic_buy_override: float | None = None
    ebay_weight: float = 1.0
    risk_status: Literal["normal", "watch", "paused", "no_buy"] = "normal"

@dataclass(frozen=True)
class CompetitorAggregate:
    """Per-channel competitor-derived input, aggregated per spec §7.4. None if unavailable."""
    online_sell: float | None
    in_mail_buy: float | None
    electronic_buy: float | None
    sources_contributing: Sequence[str]  # for breakdown rendering

@dataclass(frozen=True)
class BreakdownStep:
    """One step in the formula breakdown rendered on merchant detail."""
    label: str
    value: float | str  # numeric or sentinel
    sign: Literal["+", "-", "=", "*", "blend"]

@dataclass(frozen=True)
class ChannelResult:
    final_value: float | Literal["No", "No Data"]
    ebay_only_value: float | Literal["No", "No Data"]
    competitor_only_value: float | None
    breakdown: Sequence[BreakdownStep]

@dataclass(frozen=True)
class PriceRecommendation:
    online_sell: ChannelResult
    in_mail_buy: ChannelResult
    in_store_buy: ChannelResult
    electronic_buy: ChannelResult
    confidence: Literal["high", "medium", "low", "none"]
    no_data: bool

@dataclass(frozen=True)
class GlobalConstants:
    paypal_sell_costs: float
    online_store_postage_costs: float
    in_store_bad_debt: float
    in_mail_bad_debt: float
    competitor_electronic_markdown: float
    # eBay-related constants used by the eBay average, not direct inputs here

def compute_prices(
    ebay_sell_pct: float | None,
    ebay_confidence: Literal["high", "medium", "low", "none"],
    competitor: CompetitorAggregate,
    config: MerchantConfig,
    constants: GlobalConstants,
) -> PriceRecommendation:
    ...
```

The body of `compute_prices` implements `pricing_algorithm.md` §5; the spec is the source of truth. Do not duplicate the formula logic here.

**Test strategy:** the file `tests/fixtures/spreadsheet_baseline.json` continues to verify the faithful-port property (281 records, `ebay_weight = 1.0`). A new fixture `tests/fixtures/blending_cases.json` adds hand-computed expectations for representative merchants at `ebay_weight ∈ {0.5, 0.7, 0.9}` with synthesized competitor data, verifying spec §5 blending math. A third fixture `tests/fixtures/exclusion_cases.json` covers extended validity filter behavior (spec §6.2). All three loop the engine and assert outputs match to within ±0.001.

---

## 9. Windows deployment

### 9.1 First-time setup on your dad's machine

One-time steps, ~30 minutes total:

1. Install Python 3.12 from python.org (check "Add to PATH")
2. Install `uv`: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. Install Git for Windows
4. Clone the repo to `C:\zeal-pricing-tool`
5. `uv sync` — installs dependencies
6. Create `.env` from `.env.example` and fill in eBay API keys
7. `python -m zeal.cli init-db` — creates the SQLite file
8. `python -m zeal.cli seed` — loads merchant data from the spreadsheet
9. Run `scripts/install_scheduled_task.ps1` (as admin) — registers the daily 6 AM refresh
10. Copy `scripts/launch_dashboard.ps1` to a desktop shortcut

### 9.2 Daily use

- Scheduled task runs the refresh at 6 AM (or first wake after that)
- Operator double-clicks the desktop shortcut
- The launcher script: starts the FastAPI server in background if not running, opens default browser to `localhost:8000`, exits
- Operator works through the daily review
- Server keeps running in background; no need to close

### 9.3 Why no Windows Service

I considered installing the FastAPI app as a Windows Service (via NSSM or similar). Decided against it for v1:

- Adds a dependency and a setup step
- The launcher script approach is simpler and easier to debug
- The web app doesn't actually need to be running 24/7 — the *scheduled refresh* does, and that runs as a Task Scheduler entry independent of the web app
- If the operator wants the dashboard available without launching, we can revisit

### 9.4 Updates

When new code lands on `main`:

1. Operator (or you) runs `git pull` in the repo directory
2. Run `uv sync` if dependencies changed
3. Run `python -m zeal.cli migrate` if schema changed (no-op if not)
4. Restart the dashboard (close the terminal window, double-click shortcut again)

This is a manual process. Acceptable for one user. v2 may add an in-app "check for updates" flow if it becomes annoying.

When a competitor scraper breaks (source layout change), expect the relevant `competitor_sources.last_attempted_refresh` to update but `last_successful_refresh` to stagnate. The dashboard's Refresh Status competitor panel surfaces this. The fix is a code update + scraper test rerun; not user-actionable.

---

## 10. Backup and recovery

**What to back up:** `data/zeal.db` is the only stateful file. Everything else is in git. The database includes merchant config, eBay observations, competitor observations and source config, recommendations, and operator action history.

**How:**
- `scripts/backup_db.ps1` runs nightly via Task Scheduler at 2 AM
- Copies `data/zeal.db` to `<user>/OneDrive/zeal-pricing-tool/backups/zeal_YYYY-MM-DD.db`
- Keeps the last 30 days; older files deleted automatically
- OneDrive handles offsite replication

**Recovery from total loss:**
- Reinstall on the same or a new machine via §9.1 steps 1–6
- Replace the empty `data/zeal.db` with the most recent backup from OneDrive
- Done. No need to re-run seeding; the DB *is* the state

**Recovery from operator error** (deleted a merchant, bad config save):
- Roll back to a backup from before the error, or
- Use `merchant_config_history` to manually restore the correct values

The `merchant_config_history` and `operator_actions` tables mean most "oh no I broke it" scenarios don't even need a backup restore.

---

## 11. Build sequence

Five phases. The principle is **one thin vertical slice working end-to-end before going wide**, so we have something demoable early and can iterate.

### Phase 1 — Foundation (week 1) — COMPLETE

Goal: pricing engine works in isolation, fully tested.

- Repo scaffold (pyproject.toml, src/, tests/, ruff config)
- DB schema and migrations
- Pricing engine (`pricing/engine.py`) + confidence scoring + eBay averaging
- Pydantic models for everything
- One-time seeder script: parse the spreadsheet, populate `merchants` and `global_constants`
- Test suite: golden tests against every spreadsheet merchant
- **Acceptance:** `pytest` passes, every spreadsheet merchant's recommendation matches to ±0.001

### Phase 2 — Vertical slice (week 2)

Goal: one merchant, end-to-end, refresh to dashboard, eBay-only.

- eBay client (Browse API wrapper)
- Listing filter and merchant resolution (regex matching) — `pricing/listing_filter.py`, not `ingestion/`
- Extended validity rules per spec §6.2 (sell_pct range, suspicious keywords, partial-balance keyword exclusion)
- Daily refresh orchestrator (single merchant)
- Minimal FastAPI app, single page showing the one merchant's data
- Engine extended to return `ChannelResult` with breakdown per spec §5.6
- **Acceptance:** running the daily refresh on one merchant pulls data, computes a recommendation with breakdown, and the dashboard shows it. `ebay_weight = 1.0` default; no competitor data yet.

### Phase 3 — Go wide + competitor foundation (week 3)

Goal: all merchants, real dashboard, operator can act on recommendations. Competitor schema and manual-entry path operational.

- Refresh orchestrator handles all active merchants
- Daily Review page with priority sort
- Merchant Detail page with breakdown rendering
- Accept / Override / Skip flows
- HTMX wiring for in-place updates
- Manual "refresh now" button
- Risk flag UI (badge, config edit field, Accept-button gate for `paused`/`no_buy`)
- Competitor schema in place — `competitor_sources` and `competitor_observations` tables with migrations
- Manual competitor entry form + CSV import path
- Competitor panel on merchant detail (will show "no data yet" until Phase 4)
- **Acceptance:** operator can run a full eBay refresh, review every merchant, take action on each. Manual competitor entries appear in the dashboard. Blending math is exercised by tests but operationally everything still uses `ebay_weight = 1.0` default.

### Phase 4 — Competitor scrapers, polish, deploy (week 4–5)

Goal: deployed on operator's machine, used in real workflow, with CardCash data flowing.

- CardCash scraper + scheduled weekly refresh
- Competitor refresh orchestrator + admin panel for source management
- Config editor screen (full)
- Global constants editor
- Refresh status page (eBay + competitor sources)
- CSV export route and button
- Backup script and Task Scheduler registration
- Launcher script and desktop shortcut
- Setup documentation
- Install on operator's machine, walk through it together, capture feedback
- **Acceptance:** operator uses the tool to set prices for one full day independently. CardCash data appears for at least 50 merchants. Operator has tried adjusting `ebay_weight` on at least one merchant.

### Phase 5 — Raise scraper + post-launch refinement (on demand)

Goal: second competitor source, post-launch fixes.

- Raise scraper integration after CardCash has been running for a week+ without operational issues
- Bug fixes from Phase 4 deploy
- Iteration on operator feedback

After Phase 5: stabilize, fix bugs, gather feedback. v2 work starts only after a few weeks of real use.

---

## 12. Open questions

Tracked here so the build doesn't get blocked on missing answers, but listed so we can resolve them as we go:

- **Q1.** eBay API approval status. Pending, will update.
- **Q2.** What time of day is best for the scheduled refresh? 6 AM is a guess; ask the operator what fits his routine.
- **Q3.** Should "skip" actions be visible in the next day's review, or treated as silent? Default: visible, with a "skipped yesterday" badge.
- **Q4.** When the operator overrides, should the override become the new published price immediately, or stay as a pending change until he confirms? Default: immediate (one click is enough; faster workflow).
- **Q5.** ~~Display: percentages or dollar amounts?~~ **Resolved:** operator confirmed percentages. See decisions_log.md 2026-05-03.
- **Q6.** Currency formatting (78.5% vs 0.785 vs $78.50/$100). Use percentages with one decimal place, matching the spreadsheet's convention.
- **Q7.** When the operator updates `online_sell_override` for a Pattern A merchant, should the daily refresh skip eBay ingestion entirely for that merchant? Default: yes — no eBay calls for merchants with the override set. Saves rate-limit budget and avoids generating misleading "No Data" warnings.
- **Q8.** What's the right `competitor_electronic_markdown` value? 0.05 is provisional. Refines as data accumulates.
- **Q9.** CardCash scrape frequency — weekly is the spec default but should be re-evaluated after the first scraper runs. If the source has stricter rate limits than expected, may need to drop to bi-weekly.
- **Q10.** When a competitor scraper fails (source layout change, anti-bot block), should the operator be alerted via a dashboard banner, or is the Refresh Status page sufficient? Default: Refresh Status only; banner if operator finds the page-only version too easy to miss.

---

## 13. Out of scope (explicit)

To keep v1 scoped:

- No website integration
- No multi-user accounts or auth (single-user assumption)
- No mobile UI
- No automated price publishing
- No internal sale history integration
- No bankruptcy risk monitoring (manual `risk_status` flag is supported; automated detection is v2)
- No recency-weighted or outlier-filtered eBay averaging
- No dynamic tier reassignment
- No email/SMS alerts on failures (logs only)
- No internationalization
- Automated competitor source discovery. New competitor sources are added by code change, not by configuration.
- Real-time competitor refresh. Competitor scraping is on a daily-or-slower cadence by design.
- Competitor data export. Only Zeal's approved prices export to CSV in v1.
- Per-channel `ebay_weight`. Single weight per merchant applies to all channels uniformly.

All of these are tracked in the algorithm spec's v2 roadmap or are de novo improvements for later versions.

---

## 14. Acceptance criteria for the build

The architecture is correctly implemented when:

1. All algorithm spec acceptance criteria are met (per `pricing_algorithm.md` §13)
2. The daily eBay refresh runs successfully on a fresh Windows install with no manual intervention beyond §9.1 setup
3. The CardCash competitor refresh runs successfully on its own schedule and produces observations for at least 50 merchants within two weeks of operation
4. The operator can complete a full daily review (accept/override/skip every merchant) in <30 minutes
5. The SQLite database is automatically backed up to OneDrive nightly
6. Test coverage on `pricing/` is 100%; on `ingestion/` is ≥80%
7. Test coverage on `ingestion/competitor/` is ≥70% (lower bar acceptable because scraper logic is environment-dependent)
8. The repo passes `ruff check` and `pytest` cleanly
9. The operator has used the `ebay_weight` slider on at least one merchant during testing
10. The CSV export produces a valid file that opens cleanly in Excel and contains all merchants with non-null published prices
11. Documentation in `docs/` reflects the as-built system (this doc may need editing during build as decisions get refined)
