# Zeal Pricing Tool — Architecture

**Status:** Draft for review
**Companion to:** `pricing_algorithm.md`
**Last updated:** 2026-05-01

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
│   │   ├── listing_filter.py   # validity rules from spec §6.2
│   │   └── refresh.py          # daily refresh orchestrator
│   ├── pricing/
│   │   ├── ebay_average.py     # volume-weighted average from spec §6.3
│   │   ├── confidence.py       # confidence scoring from spec §6.4
│   │   └── engine.py           # the four channel formulas from spec §5
│   ├── web/
│   │   ├── app.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── dashboard.py    # main views
│   │   │   ├── merchants.py    # config editor
│   │   │   ├── actions.py      # accept/override/skip
│   │   │   └── admin.py        # global constants, manual refresh
│   │   ├── templates/          # Jinja2 + HTMX
│   │   │   ├── base.html
│   │   │   ├── dashboard.html
│   │   │   └── partials/
│   │   └── static/
│   │       ├── style.css       # Tailwind output
│   │       └── htmx.min.js
│   └── jobs/
│       └── daily_refresh.py    # entry point for Task Scheduler
├── tests/
│   ├── conftest.py
│   ├── test_pricing_engine.py  # golden tests vs spreadsheet
│   ├── test_ebay_average.py
│   ├── test_confidence.py
│   ├── test_listing_filter.py
│   └── fixtures/
│       └── spreadsheet_baseline.json   # expected outputs for every merchant
├── scripts/
│   ├── seed_from_spreadsheet.py        # one-time merchant import
│   ├── backup_db.ps1                   # PowerShell, copies SQLite to OneDrive
│   ├── install_scheduled_task.ps1      # registers Windows scheduled task
│   └── launch_dashboard.ps1            # double-clickable launcher
└── data/
    └── .gitkeep                # SQLite file lives here; contents gitignored
```

The split between `ingestion`, `pricing`, and `web` matters: the algorithm code (`pricing/`) has zero dependencies on web framework or database, which means it's trivially testable and could be reused in another context without rework.

---

## 4. Component map

Six components, with explicit dependencies:

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

1. **eBay Ingestion** — Calls eBay Browse API, paginates, filters listings per spec §6.2, writes raw observations to `ebay_observations`. Idempotent; safe to re-run. Talks only to eBay and the database.

2. **Pricing Engine** — Pure functions (no I/O). Reads merchant config and observations from arguments, returns recommendation objects. The formulas from spec §5 live here. Heavily tested.

3. **Daily Refresh Orchestrator** — The conductor. For each active merchant: trigger ingestion, compute the eBay average, run the pricing engine, write recommendations. Logs results to `refresh_runs` table.

4. **Database** — SQLite at `data/zeal.db`. Schema in §6. Migrations are numbered SQL files applied at startup.

5. **Dashboard (FastAPI)** — The operator UI. Read-heavy; the only writes are operator actions (accept/override/skip) and config edits.

6. **Scheduler** — Windows Task Scheduler entry that runs `python -m zeal.jobs.daily_refresh`. No code in our repo; just a registration script.

---

## 5. Daily refresh — data flow

What happens at 6 AM:

1. Task Scheduler fires `python -m zeal.jobs.daily_refresh`
2. The job creates a row in `refresh_runs` with status `running`
3. For each `is_active = 1` merchant:
   - Query eBay Browse API for sold listings matching the merchant's regex, last 90 days, US only
   - For each listing returned: apply validity filters (spec §6.2), upsert into `ebay_observations` (deduped by `listing_id`)
   - Compute `ebay_sell_pct` per spec §6.3 (volume-weighted avg of last 10 valid)
   - Compute confidence per spec §6.4
   - Upsert one row in `ebay_summary` for today
   - Load merchant config
   - Run pricing engine → four channel prices
   - Insert into `price_recommendations`
4. Mark `refresh_runs` row `completed`, with counts
5. If anything fails: mark `failed`, write error to log, continue with next merchant (one bad merchant doesn't break the run)

**Rate limiting:** eBay Browse API allows 5,000 calls/day on free tier. ~300 merchants × ~3 paginated requests each = ~900 calls. Well under limit. We add a 100ms sleep between calls to be polite.

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
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id   TEXT NOT NULL REFERENCES merchants(merchant_id),
    listing_id    TEXT NOT NULL UNIQUE,                   -- eBay's item id
    sold_at       TEXT NOT NULL,                          -- when the eBay sale closed
    face_value    REAL NOT NULL,
    sale_price    REAL NOT NULL,                          -- includes shipping
    title         TEXT NOT NULL,                          -- raw, for debugging
    raw_payload   TEXT,                                   -- JSON of full eBay item
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_obs_merchant_date ON ebay_observations(merchant_id, sold_at DESC);
```

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

**`refresh_runs`** — log of each daily refresh, for ops visibility

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
- **Eligibility is per-channel.** The `in_store_eligible`, `in_mail_eligible`, `electronic_eligible` flags map directly to the spreadsheet's `"No"` convention in columns C, E, D respectively. Any combination is permitted (e.g. Home Depot eStore Credit is electronic-only; merch-credit variants are electronic-disabled).
- **Override fields are surgical.** `online_sell_override` and `electronic_buy_override` exist for specific spreadsheet patterns where the standard formula doesn't apply: Pattern A (local NC merchants, ~25 today) and Home Depot eStore Credit (1 merchant). When `NULL`, the standard formula path runs. The engine checks overrides before deriving from eBay input or in-mail buy.
- **No FK cascades on delete.** Merchants are never deleted, only deactivated (`is_active = 0`). This preserves history.
- **Snapshot config in `price_recommendations`.** When an old recommendation is reviewed months later, we want to know what the config *was at the time*, not what it is now. The JSON snapshot is the cheapest way to get this.
- **No dedicated `users` table.** Single user, no auth needed.

---

## 7. Dashboard — screens and flows

Five screens. Mobile-unfriendly is fine (operator works at a desktop).

### 7.1 Daily Review (home page)

The screen the operator opens every morning. Three sections:

- **High priority** — merchants with delta >2pp from current published price, or confidence dropped to low/none, or no data
- **Medium priority** — delta 0.5–2pp
- **Low priority** — collapsed by default

Each merchant row shows: display name, current published prices, recommended prices, deltas, confidence badge, action buttons (Accept / Override / Skip).

Action buttons are HTMX-powered: clicking Accept fires a POST and the row updates in place. No page reload.

### 7.2 Merchant Detail

One merchant, all the context:

- Current published prices and their recommendation source
- Today's recommendation with input breakdown (eBay %, confidence, sample size, freshness)
- Recent eBay observations table (last 30 listings, sortable)
- Price history chart (last 90 days, all four channels)
- Operator action history for this merchant
- Override interface

### 7.3 Config Editor

Per-merchant: edit margins, e-bonus, eBay differential, regexes, electronic-eligible flag. Every save logs to `merchant_config_history` and prompts for an optional reason.

Bulk operations are out of scope for v1 (operator edits one at a time).

### 7.4 Global Constants

Single page listing the ~7 global constants with current value and edit button. Same logging pattern as merchant config.

### 7.5 Refresh Status

Last successful refresh time, last failure if any, "Refresh now" button. Shows in-progress status when a refresh is running.

---

## 8. Pricing engine — implementation outline

The algorithm is in `src/zeal/pricing/engine.py`. Pure functions, no side effects, no I/O. This makes it the most testable part of the system.

```python
from dataclasses import dataclass
from typing import Literal

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

@dataclass(frozen=True)
class GlobalConstants:
    paypal_sell_costs: float
    online_store_postage_costs: float
    in_store_bad_debt: float
    in_mail_bad_debt: float
    # eBay-related constants used by the eBay average, not direct inputs here

@dataclass(frozen=True)
class PriceRecommendation:
    online_sell: float | None
    in_mail_buy: float | None
    in_store_buy: float | None
    electronic_buy: float | Literal["No"] | None
    no_data: bool
    confidence: Literal["high", "medium", "low", "none"]

def compute_prices(
    ebay_sell_pct: float | None,
    confidence: Literal["high", "medium", "low", "none"],
    config: MerchantConfig,
    constants: GlobalConstants,
) -> PriceRecommendation:
    # Online sell: override wins, else eBay-derived, else No Data sentinel
    if config.online_sell_override is not None:
        online_sell: float | str = config.online_sell_override
    elif ebay_sell_pct is None:
        online_sell = "No Data"
    else:
        online_sell = ebay_sell_pct - config.ebay_differential

    # In-mail: eligibility wins, then No Data propagation, then formula
    if not config.in_mail_eligible:
        in_mail_buy: float | str = "No"
    elif isinstance(online_sell, str):  # "No Data"
        in_mail_buy = "No Data"
    else:
        in_mail_buy = (
            online_sell
            - config.in_mail_margin
            - constants.paypal_sell_costs
            - constants.in_mail_bad_debt
            - constants.online_store_postage_costs
        )

    # In-store: parallel structure
    if not config.in_store_eligible:
        in_store_buy: float | str = "No"
    elif isinstance(online_sell, str):
        in_store_buy = "No Data"
    else:
        in_store_buy = (
            online_sell
            - config.in_store_margin
            - constants.paypal_sell_costs
            - constants.online_store_postage_costs
            - constants.in_store_bad_debt
        )

    # Electronic: eligibility, then override (bypasses in-mail dependency), then formula
    if not config.electronic_eligible:
        electronic_buy: float | str = "No"
    elif config.electronic_buy_override is not None:
        electronic_buy = config.electronic_buy_override
    elif isinstance(in_mail_buy, str):  # "No" or "No Data"
        electronic_buy = "No Data"
    else:
        assert config.e_bonus is not None
        electronic_buy = in_mail_buy - config.e_bonus

    no_data = online_sell == "No Data"
    return PriceRecommendation(
        online_sell=online_sell if not isinstance(online_sell, str) else None,
        in_mail_buy=in_mail_buy if not isinstance(in_mail_buy, str) else None,
        in_store_buy=in_store_buy if not isinstance(in_store_buy, str) else None,
        electronic_buy=electronic_buy if not isinstance(electronic_buy, str) else electronic_buy,
        no_data=no_data,
        confidence=confidence,
    )
```

Note: this is illustrative pseudocode. The actual implementation may use a richer return type that distinguishes `"No"` from `"No Data"` per channel. Decide during the engine implementation session.

**Test strategy:** the file `tests/fixtures/spreadsheet_baseline.json` contains expected outputs for every merchant in the source spreadsheet, given each merchant's config and an eBay input. The test loops every fixture and asserts the engine's output matches to within ±0.001. If we touch the engine and break something, the test catches it.

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

---

## 10. Backup and recovery

**What to back up:** `data/zeal.db` is the only stateful file. Everything else is in git.

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

Four phases, ~4 weeks total. The principle is **one thin vertical slice working end-to-end before going wide**, so we have something demoable early and can iterate.

### Phase 1 — Foundation (week 1)

Goal: pricing engine works in isolation, fully tested.

- Repo scaffold (pyproject.toml, src/, tests/, ruff config)
- DB schema and migrations
- Pricing engine (`pricing/engine.py`) + confidence scoring + eBay averaging
- Pydantic models for everything
- One-time seeder script: parse the spreadsheet, populate `merchants` and `global_constants`
- Test suite: golden tests against every spreadsheet merchant
- **Acceptance:** `pytest` passes, every spreadsheet merchant's recommendation matches to ±0.001

### Phase 2 — Vertical slice (week 2)

Goal: one merchant, end-to-end, refresh to dashboard.

- eBay client (Browse API wrapper)
- Listing filter and merchant resolution (regex matching)
- Daily refresh orchestrator (single merchant)
- Minimal FastAPI app, single page showing the one merchant's data
- **Acceptance:** running `python -m zeal.jobs.daily_refresh --merchant home_depot` pulls real eBay data, computes a recommendation, and the dashboard shows it

### Phase 3 — Go wide (week 3)

Goal: all merchants, real dashboard, operator can act on recommendations.

- Refresh orchestrator handles all active merchants
- Daily Review page with priority sorting
- Merchant Detail page
- Accept / Override / Skip flows
- HTMX wiring for in-place updates
- Manual "refresh now" button
- **Acceptance:** operator can run a full refresh, review every merchant, take action on each, and the actions log correctly

### Phase 4 — Polish and deploy (week 4)

Goal: deployed on your dad's machine, used in real workflow.

- Config editor screen
- Global constants editor
- Refresh status page
- Backup script and Task Scheduler registration
- Launcher script and desktop shortcut
- Setup documentation
- Install on your dad's machine, walk through it together, capture feedback
- **Acceptance:** your dad uses the tool to set prices for one full day independently

After phase 4: stabilize, fix bugs, gather feedback. v2 work starts only after a few weeks of real use.

---

## 12. Open questions

Tracked here so the build doesn't get blocked on missing answers, but listed so we can resolve them as we go:

- **Q1.** eBay API approval status. Pending, will update.
- **Q2.** What time of day is best for the scheduled refresh? 6 AM is a guess; ask the operator what fits his routine.
- **Q3.** Should "skip" actions be visible in the next day's review, or treated as silent? Default: visible, with a "skipped yesterday" badge.
- **Q4.** When the operator overrides, should the override become the new published price immediately, or stay as a pending change until he confirms? Default: immediate (one click is enough; faster workflow).
- **Q5.** Display: percentages or dollar amounts? Spreadsheet uses percentages; assume same. Confirm with operator.
- **Q6.** Currency formatting (78.5% vs 0.785 vs $78.50/$100). Use percentages with one decimal place, matching the spreadsheet's convention.
- **Q7.** When the operator updates `online_sell_override` for a Pattern A merchant, should the daily refresh skip eBay ingestion entirely for that merchant? Default: yes — no eBay calls for merchants with the override set. Saves rate-limit budget and avoids generating misleading "No Data" warnings.

---

## 13. Out of scope (explicit)

To keep v1 scoped:

- No website integration
- No multi-user accounts or auth (single-user assumption)
- No mobile UI
- No automated price publishing
- No competitor data ingestion (eBay only)
- No internal sale history integration
- No bankruptcy risk monitoring
- No recency-weighted or outlier-filtered eBay averaging
- No dynamic tier reassignment
- No email/SMS alerts on failures (logs only)
- No internationalization

All of these are tracked in the algorithm spec's v2 roadmap or are de novo improvements for later versions.

---

## 14. Acceptance criteria for the build

The architecture is correctly implemented when:

1. All algorithm spec acceptance criteria are met (per `pricing_algorithm.md` §12)
2. The daily refresh runs successfully on a fresh Windows install with no manual intervention beyond §9.1 setup
3. The operator can complete a full daily review (accept/override/skip every merchant) in <30 minutes
4. The SQLite database is automatically backed up to OneDrive nightly
5. Test coverage on `pricing/` is 100%; on `ingestion/` is ≥80%
6. The repo passes `ruff check` and `pytest` cleanly
7. Documentation in `docs/` reflects the as-built system (this doc may need editing during build as decisions get refined)
