# Zeal Pricing Tool — Architecture

**Status:** Draft for review — v1 scope realigned 2026-05-04
**Companion to:** `pricing_algorithm.md`
**Last updated:** 2026-05-04

This document specifies how the v1 pricing tool is built and deployed. It assumes the algorithm spec is the source of truth for *what* the system computes; this doc covers *how*.

---

## 1. Goals and non-goals

**Goals:**
- A working pricing dashboard the operator runs on demand to review pricing for ~300 merchants
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
- In-app configuration editing
- Automated competitor source discovery
- Website integration as a v1 feature

---

## 2. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | Best ecosystem for HTTP scraping, data handling, eBay API |
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
├── pyproject.toml
├── .python-version             # 3.12
├── .env.example
├── .gitignore
├── docs/
│   ├── pricing_algorithm.md
│   ├── architecture.md
│   ├── decisions_log.md
│   └── spreadsheet_recon.md
├── src/zeal/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py                  # `zeal serve`, `zeal refresh`, `zeal seed`, `zeal init-db`
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql
│   │   ├── connection.py
│   │   └── migrations/
│   ├── models/
│   │   ├── merchant.py
│   │   ├── pricing.py
│   │   ├── ebay.py
│   │   └── competitor.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── ebay_client.py
│   │   ├── refresh.py          # on-demand refresh orchestrator
│   │   └── competitor/
│   │       ├── __init__.py
│   │       ├── base.py         # CompetitorSource protocol
│   │       ├── cardcash.py     # v1 single source
│   │       └── refresh.py      # competitor refresh helper
│   ├── pricing/
│   │   ├── __init__.py
│   │   ├── ebay_average.py     # spec §6.3
│   │   ├── listing_filter.py   # spec §6.2; pure functions
│   │   ├── competitor_aggregate.py  # spec §7
│   │   ├── confidence.py       # spec §6.4 and §7.5
│   │   ├── blending.py         # spec §5.7; engine structure for v2
│   │   └── engine.py           # spec §5; the four channel formulas
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI app, runs background refresh task
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── dashboard.py    # GET / — spreadsheet-style list
│   │   │   ├── merchant.py     # GET /merchant/{id} — detail
│   │   │   └── refresh.py      # POST /refresh, GET /refresh/status
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── dashboard.html
│   │   │   ├── merchant_detail.html
│   │   │   └── partials/
│   │   │       ├── breakdown.html
│   │   │       ├── refresh_progress.html
│   │   │       └── competitor_panel.html
│   │   └── static/
│   │       ├── style.css
│   │       └── htmx.min.js
│   └── jobs/                   # placeholder; v1 has no scheduled jobs
├── tests/
│   ├── conftest.py
│   ├── test_pricing_engine_baseline.py
│   ├── test_ebay_average.py
│   ├── test_confidence.py
│   ├── test_listing_filter.py
│   ├── test_blending.py        # exercises engine paths inactive in v1
│   ├── test_competitor_aggregate.py
│   ├── test_parser.py
│   └── fixtures/
│       └── spreadsheet_baseline.json
├── scripts/
│   ├── seed_from_spreadsheet.py
│   └── launch_dashboard.ps1
└── data/
    └── .gitkeep
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
   │  eBay + CardCash  │   │  pure functions   │
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

2. **Ingestion** — eBay client (Browse API wrapper) and competitor scraper (CardCash). Both are invoked from the background refresh task. The eBay client paginates, filters listings per spec §6.2, and writes to `ebay_observations` with `validity_status` and `exclusion_reason`. The CardCash scraper writes to `competitor_observations`. Both are idempotent and safe to re-run.

3. **Dashboard (FastAPI)** — the operator UI plus refresh orchestration. Two screens (list view, merchant detail) plus three control routes (`POST /refresh`, `GET /refresh/status`, `GET /merchant/{id}`). The refresh task runs as a FastAPI background task in the same process; status is tracked in the `refresh_runs` table and exposed via the status endpoint.

4. **Database** — SQLite at `data/zeal.db`. Schema in §6. The `price_recommendations` table is append-only and forms the system of record for all pricing recommendations the tool has ever produced.

---

## 5. Refresh data flow

Refresh is on-demand only. There is no scheduled job in v1.

**What happens when the operator clicks "Refresh now":**

1. Browser issues `POST /refresh`. Server checks `refresh_runs` for an in-flight run; if one exists, returns 409. Otherwise creates a row in `refresh_runs` with status `running` and dispatches a FastAPI background task.
2. Browser begins polling `GET /refresh/status` every 2 seconds. The status response is `{state, processed, total, started_at, error?}`.
3. The background task iterates active merchants:
   - For each merchant: query eBay Browse API for sold listings matching the merchant's regex, last 90 days, US only.
   - For each listing: apply validity filters (spec §6.2), upsert into `ebay_observations` (deduped by `listing_id`), recording `validity_status` and `exclusion_reason`.
   - Compute `ebay_sell_pct` per spec §6.3, eBay confidence per spec §6.4. Upsert one row in `ebay_summary` keyed by `(merchant_id, today)`.
   - Compute the recommendation by calling `compute_prices(ebay_sell_pct, ebay_confidence, competitor=None_or_aggregate, config, constants)`. v1 always passes `ebay_weight = 1.0` (read from merchant config) and the recommendation equals the eBay-only output. Insert into `price_recommendations`.
   - Update the `refresh_runs` row's `processed` count.
4. Separately, the task also refreshes competitor data (CardCash) for the active merchants. Competitor refresh runs after eBay is complete to keep the progress signal interpretable. Each merchant's CardCash scrape writes to `competitor_observations`; failures log and skip that merchant.
5. When all merchants are processed (or an unrecoverable error occurs): mark `refresh_runs` row `completed` (or `failed`/`partial`), set `completed_at`. The status endpoint surfaces this and the browser stops polling.
6. The dashboard re-renders the list view to show the new recommendations.

**Rate limiting:** eBay Browse API allows 5,000 calls/day on free tier. ~300 merchants x ~3 paginated requests each is ~900 calls per refresh. A 100ms sleep between calls keeps us comfortably polite. CardCash adds 500-1000ms between requests because the operator may run multiple refreshes per day and the per-day total should still stay low.

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

**`merchant_config_history`** — retained for direct-DB changes and v2 editor readiness

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
- **Override fields are surgical.** `online_sell_override` and `electronic_buy_override` exist for specific spreadsheet patterns where the standard formula does not apply. When `NULL`, the standard formula path runs.
- **`ebay_weight` stays in schema.** It defaults to 1.0 and v1 provides no UI to change it. Keeping the column avoids churn and preserves the v2 blending path.
- **No FK cascades on delete.** Merchants are never deleted, only deactivated (`is_active = 0`). This preserves history.
- **Snapshot config in `price_recommendations`.** When an old recommendation is reviewed months later, we want to know what the config was at the time, not what it is now. The JSON snapshot is the cheapest way to get this.
- **`price_recommendations` is append-only.** Every refresh writes new rows. The merchant detail page reads the historical trail. There is no `current_recommendation` table; "current" means "most recent row by `computed_at` for this merchant."
- **No `published_prices` or `operator_actions` tables.** v1 does not track which recommendations the operator chose to apply. v2 may reintroduce these once the operator's workflow is stable enough to define what "published" means in this tool's context.
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
- **Formula breakdown** — per-channel worked formula from `BreakdownStep` sequences (spec §5.6). Rendered as a stack of `[label] [sign] [value]` rows leading to the final value.
- **Recent eBay observations** — table of the most recent 30 valid listings used in the average. Sortable by sold date, face value, sale price, computed sell percentage.
- **Excluded eBay observations** — collapsible table of listings filtered out, with `exclusion_reason`. Useful for debugging the regex and validity rules.
- **Competitor reference panel** — for each configured competitor source (v1: CardCash only), the most recent observation per channel: `price_pct`, `availability`, `confidence`, `observed_at`, source URL. Reference-only — explicitly marked as not feeding the recommendation in v1.
- **Recommendation history** — line chart of all four channels over the last 90 days of refreshes. Hover for tooltip with the exact value at that timestamp.
- **Recent refresh status for this merchant** — last 10 refreshes, success/skip/error.

No edit controls in v1.

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

@dataclass(frozen=True)
class CompetitorAggregate:
    """Per-channel competitor-derived input, aggregated per spec §7.4. None if unavailable."""
    online_sell: float | None
    in_mail_buy: float | None
    electronic_buy: float | None
    sources_contributing: Sequence[str]

@dataclass(frozen=True)
class BreakdownStep:
    """One step in the formula breakdown rendered on merchant detail."""
    label: str
    value: float | str
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

In v1 the dashboard always passes `config.ebay_weight = 1.0`, so the recommendation equals the eBay-only path output regardless of `competitor` content. The engine still computes and returns competitor-only and blended values internally; they are unit-tested but not surfaced to the operator. v2 introduces UI to vary `ebay_weight` per merchant.

**Test strategy:** the file `tests/fixtures/spreadsheet_baseline.json` continues to verify the faithful-port property (281 records, `ebay_weight = 1.0`). `tests/fixtures/blending_cases.json` verifies engine math at non-1.0 weights as a v2 guardrail. `tests/fixtures/exclusion_cases.json` covers extended validity filter behavior (spec §6.2). All loop the engine and assert outputs match to within +/-0.001.

---

## 9. Windows deployment

### 9.1 First-time setup on the operator's machine

One-time, ~20 minutes:

1. Install Python 3.12 from python.org (check "Add to PATH").
2. Install `uv`: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. Install Git for Windows.
4. Clone the repo to `C:\zeal-pricing-tool`.
5. `uv sync` — installs dependencies.
6. Create `.env` from `.env.example` and fill in eBay API keys.
7. `python -m zeal.cli init-db` — creates the SQLite file at `data/zeal.db`.
8. `python -m zeal.cli seed` — loads merchant data from the spreadsheet.
9. Copy `scripts/launch_dashboard.ps1` to a desktop shortcut.

### 9.2 Daily use

- Operator double-clicks the desktop shortcut.
- The launcher starts the FastAPI server in a console window (kept open while the dashboard is in use) and opens the default browser to `localhost:8000`.
- Operator clicks "Refresh now" when he wants new pricing data, watches the progress bar, then reviews the recommendations.
- When done, operator closes the console window. Closing only the browser leaves the server running, which is harmless but wastes a process.

### 9.3 Updates

When new code lands on `main`:

1. Operator (or developer) runs `git pull` in the repo directory.
2. Run `uv sync` if dependencies changed.
3. Run `python -m zeal.cli migrate` if schema changed (no-op if not).
4. Restart the dashboard (close console, double-click shortcut).

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

### Phase 2 — Read-only viewer with synthetic data

Goal: the dashboard structure exists and renders, before any live ingestion is wired up.

- FastAPI app skeleton, two routes (`GET /`, `GET /merchant/{id}`)
- Templates for both screens
- Spreadsheet-style list view rendering data from `price_recommendations`
- Merchant detail rendering breakdown, history chart, etc.
- Seeder script extended to write a fake "recommendation" row per merchant from the spreadsheet's computed values, so the UI has data to render without eBay access
- `zeal serve` CLI command, launcher script, desktop shortcut workflow validated

**Acceptance:** operator can open the dashboard, scroll through all merchants, click any one to see detail. No refresh button yet; the data is the seeded synthetic recommendations.

### Phase 3 — On-demand eBay refresh

Goal: real eBay data, real refresh button, real progress bar.

- eBay Browse API client (Phase 2 prerequisite: API access approved)
- Listing filter (extended validity rules per spec §6.2)
- Refresh orchestrator running as FastAPI background task
- `POST /refresh`, `GET /refresh/status` routes
- Progress bar in list view, polling every 2s
- Delta-from-last-run and max-abs-delta-over-N columns and sorting

**Acceptance:** operator clicks "Refresh now," watches the progress bar, sees updated recommendations sorted by movement. Competitor panel on merchant detail shows "no competitor data yet."

### Phase 4 — CardCash competitor scraper

Goal: competitor data flowing.

- CompetitorSource protocol (`ingestion/competitor/base.py`)
- CardCash scraper (`ingestion/competitor/cardcash.py`)
- Competitor refresh integrated into the background refresh task (runs after eBay refresh completes)
- Competitor reference panel on merchant detail

**Acceptance:** after a refresh, CardCash rates appear on the merchant detail page for at least 50 merchants. The recommendation is unchanged — competitor data is reference-only.

### Phase 5 — Polish and stabilize

Open-ended: bug fixes from operator feedback, UI tweaks, edge case handling. Begins after Phase 4 has been used in real workflow for a week+.

After Phase 5: stabilize. v2 (per `pricing_algorithm.md` §11) starts only after the operator has used v1 long enough to have informed feedback on which v2 improvements are worth the effort.

---

## 12. Open questions

Tracked here so the build does not get blocked on missing answers, but listed so we can resolve them as we go:

- **Q1.** eBay API approval status. Pending, will update.
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
- No in-app config editor — merchant config is seeded from the spreadsheet at install; changes require direct DB edit.
- No `ebay_weight` UI — field exists in schema and engine, locked at 1.0 in v1.
- No internal sale history integration.
- No automated bankruptcy or risk monitoring.
- No recency-weighted or outlier-filtered eBay averaging beyond range checks and keyword exclusions.
- No dynamic tier reassignment.
- No email/SMS alerts on failures (logs only).
- No internationalization.
- No automated competitor source discovery.
- Only one competitor source in v1 (CardCash). Additional sources are v2.
- No automated database backup — manual copy as documented in §10.

All of these are tracked in the algorithm spec's v2 roadmap or are de novo improvements for later versions.

---

## 14. Acceptance criteria for the build

The architecture is correctly implemented when:

1. All algorithm spec acceptance criteria are met (per `pricing_algorithm.md` §13).
2. The dashboard launches via the desktop shortcut and renders the list view of all active merchants.
3. The "Refresh now" button completes a full refresh of all active merchants without manual intervention beyond the click. Progress bar updates as merchants are processed.
4. The CardCash scraper produces observations for at least 50 merchants on a single refresh.
5. The merchant detail page renders formula breakdown, recent eBay observations, competitor reference panel, and recommendation history chart for every merchant.
6. The operator can complete a full review (scan list, drill into outliers, return to list) in under 30 minutes for the typical case.
7. Test coverage on `pricing/` is 100%; on `ingestion/` is >=80%.
8. Test coverage on `ingestion/competitor/` is >=70% (lower bar acceptable because scraper logic is environment-dependent).
9. The repo passes `ruff check` and `pytest` cleanly.
10. The pure-function boundary in `pricing/` is preserved: no FastAPI, SQLite, or httpx imports anywhere in the package. Verified by an import-linter rule in CI.
11. Documentation in `docs/` reflects the as-built system.
