# Architecture Doc Revision Plan

This file specifies the changes to apply to `docs/architecture.md` to reflect the v1 scope expansion documented in `docs/decisions_log.md` (three entries dated 2026-05-04) and `docs/pricing_algorithm.md` (rewritten 2026-05-04). It is the authoritative spec for the architecture revision session.

This file is a one-time scratch spec. Once `architecture.md` is updated, this file can be deleted.

---

## Front matter

Update status line and date:

```markdown
**Status:** Draft for review — v1 scope expanded 2026-05-04
**Companion to:** `pricing_algorithm.md`
**Last updated:** 2026-05-04
```

## §1 Goals and non-goals

No change to goals. Add one bullet to the non-goals list:

```markdown
**Non-goals:**
- Multi-user support
- Real-time pricing (daily is enough)
- Hosted/SaaS deployment
- Mobile app or responsive design beyond "looks fine on a laptop"
- Automated price publishing
- Automated competitor source discovery (CardCash and Raise are configured manually; new sources added by operator+developer collaboration, not auto-detection)
```

## §2 Stack

Add one row to the stack table, after the `httpx` row:

```markdown
| HTML parsing | selectolax or BeautifulSoup4 | For competitor source scraping. selectolax preferred (faster, lower memory). |
```

## §3 Repository layout

Update the repo tree. Two structural changes:

1. `listing_filter.py` lives in `pricing/`, not `ingestion/`. If the current tree shows it under ingestion, move it.
2. New paths for competitor ingestion, new pricing modules, new web routes and templates.

Apply this revised tree (showing only the changed sections; leave the rest of the tree as currently written):

```
├── src/zeal/
│   ├── ...
│   ├── ingestion/
│   │   ├── ebay_client.py      # eBay client wrapper
│   │   ├── refresh.py          # daily refresh orchestrator
│   │   ├── competitor/         # competitor source ingestion
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # CompetitorSource protocol
│   │   │   ├── cardcash.py     # CardCash scraper (v1 first source)
│   │   │   ├── raise_.py       # Raise scraper (Phase 5)
│   │   │   ├── manual.py       # Manual entry / CSV import path
│   │   │   └── refresh.py      # Per-source competitor refresh orchestrator
│   ├── pricing/
│   │   ├── ebay_average.py     # volume-weighted average from spec §6.3
│   │   ├── listing_filter.py   # validity rules from spec §6.2
│   │   ├── competitor_aggregate.py  # per-source and cross-source aggregation per spec §7
│   │   ├── confidence.py       # confidence scoring from spec §6.4 and §7.5
│   │   ├── blending.py         # eBay/competitor blending per spec §5
│   │   └── engine.py           # the four channel formulas from spec §5
│   ├── web/
│   │   ├── ...
│   │   ├── routes/
│   │   │   ├── dashboard.py
│   │   │   ├── merchants.py
│   │   │   ├── actions.py
│   │   │   ├── admin.py
│   │   │   ├── competitor.py   # competitor data import / view routes
│   │   │   └── export.py       # CSV export route
│   │   ├── templates/
│   │   │   ├── ...
│   │   │   ├── partials/
│   │   │   │   ├── ...
│   │   │   │   ├── breakdown.html       # formula breakdown rendering
│   │   │   │   ├── risk_badge.html      # risk_status display
│   │   │   │   └── competitor_panel.html # competitor data on merchant detail
```

Note on `raise_.py`: trailing underscore because `raise` is a Python keyword. Module cannot be named `raise.py`.

## §4 Component map

Update the ASCII diagram to show competitor ingestion as a parallel component to eBay ingestion. Both feed the database; the daily refresh orchestrator coordinates eBay; competitor refresh runs on a separate cadence (see §5).

Replace the current ASCII diagram with:

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

Add a new component description for competitor ingestion. Insert as the new component #2; renumber subsequent components by one:

```markdown
2. **Competitor Ingestion** — One module per source, all conforming to a `CompetitorSource` protocol. CardCash scrapes HTML on weekly cadence. Manual import accepts CSV uploads. Raise integrates after CardCash has been operationally validated. Each source writes to `competitor_observations` with confidence and availability flags. Talks only to its source and the database.
```

The Pricing Engine becomes #3, the Daily Refresh Orchestrator #4, the Database #5, the Dashboard #6, and the Scheduler #7.

## §5 Daily refresh — data flow

Insert this paragraph before the existing "Rate limiting" paragraph:

```markdown
**Competitor refresh cadence.** Each competitor source has its own scheduled refresh, default weekly. Sources are configured via `competitor_sources` table. The competitor refresh orchestrator is a parallel job to the eBay daily refresh; both write to the database and can run concurrently. Cross-source aggregation (per spec §7.4) happens at recommendation time, reading whatever observations are currently in the database, so per-source refresh timing doesn't need coordination.
```

Extend the existing "Rate limiting" paragraph with one sentence:

```markdown
**Rate limiting:** [keep existing eBay text]. Competitor scrapers add a 500–1000ms sleep between requests, longer than eBay's 100ms because competitor sources are not designed for bulk programmatic access and we want to be visibly polite. CardCash specifically should be tested at this cadence and adjusted if the source rate-limits us.
```

## §6.1 Database schema — modified `merchants`

Replace the existing `merchants` CREATE TABLE with:

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
    -- v1 expansion fields:
    ebay_weight              REAL NOT NULL DEFAULT 1.0 CHECK (ebay_weight >= 0.0 AND ebay_weight <= 1.0),
    risk_status              TEXT NOT NULL DEFAULT 'normal' CHECK (risk_status IN ('normal','watch','paused','no_buy')),
    risk_note                TEXT,
    -- audit:
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## §6.1 Database schema — modified `ebay_observations`

Replace the existing `ebay_observations` CREATE TABLE and indexes with:

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
    -- v1 expansion fields:
    validity_status     TEXT NOT NULL DEFAULT 'valid' CHECK (validity_status IN ('valid','excluded','suspicious')),
    exclusion_reason    TEXT,
    -- audit:
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_obs_merchant_date ON ebay_observations(merchant_id, sold_at DESC);
CREATE INDEX idx_obs_validity ON ebay_observations(merchant_id, validity_status);
```

The `'suspicious'` value is reserved for v1.1; v1 application code does not produce or consume it. Including it in the CHECK constraint avoids a schema migration when v1.1 lands.

## §6.1 Database schema — new `competitor_sources`

Add this new table:

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

## §6.1 Database schema — new `competitor_observations`

Add this new table and its indexes:

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

## §6.2 Schema design notes — additions

Append two bullets to the existing list of schema design notes:

```markdown
- **Competitor data is reference, not authoritative.** Competitor observations exist for blending and operator context. They are not used by the spreadsheet-faithful baseline and at `ebay_weight = 1.0` they are computed but not consumed.
- **Per-source schema, not per-merchant-per-source schema.** `competitor_observations` stores one row per observation, indexed by merchant, source, and time. Cross-source aggregation (per spec §7.4) happens at query time, not at storage time. This keeps writes simple and lets aggregation rules evolve without re-ingestion.
```

## §7.1 Daily Review — extension

Update the merchant row content description to:

```markdown
Each merchant row shows: display name, risk badge if not normal, current published prices, recommended prices, deltas, confidence badge, competitor-influence indicator (small icon when ebay_weight < 1.0 and competitor data contributed), action buttons (Accept / Override / Skip).
```

The remainder of §7.1 (priority sort, HTMX update behavior) is unchanged.

## §7.2 Merchant Detail — restructured content list

Replace the existing content bullet list with:

```markdown
- Current published prices and their recommendation source
- Today's recommendation with structured formula breakdown (eBay path, competitor path, blending — per spec §5.6)
- eBay weight slider with current value (operator can adjust here or in config editor)
- Risk status badge and note (if not 'normal')
- eBay sell percentage used, sample size, confidence, freshness
- Recent eBay observations table (last 30 listings, sortable)
- Excluded eBay observations table (with `exclusion_reason` per spec §6.2) — collapsible, expanded on demand
- Competitor data panel — per-source observations, channel, price_pct, availability, confidence, observed_at, source URL link
- Price history chart (last 90 days, all four channels)
- Operator action history for this merchant
- Override interface
```

## §7.3 Config Editor — extension

Replace the editable-fields description with:

```markdown
Per-merchant: edit margins, e-bonus, eBay differential, regexes, electronic-eligible flag, `ebay_weight`, `risk_status`, `risk_note`. Every save logs to `merchant_config_history` and prompts for an optional reason.
```

## §7.5 Refresh Status — extension

Add this paragraph after the existing eBay-refresh description:

```markdown
**Competitor sources panel:** for each row in `competitor_sources`, show: source name, last successful refresh (with staleness color: green ≤ refresh_interval_days, yellow up to 2x, red beyond), last attempted refresh, observation count in last 30 days. Manual "Refresh now" button per source.
```

## §7.6 Competitor Data Admin — new section

Insert as new §7.6:

```markdown
### 7.6 Competitor Data Admin

A dedicated section for working with competitor data at the source level:

- **Source list** — same content as the Refresh Status panel, plus enable/disable toggle and refresh interval edit.
- **Manual entry form** — operator selects merchant, source, channel, enters price_pct and availability. Used for sources without a scraper, or to override a scraped value the operator has reason to distrust.
- **CSV import** — upload a CSV with columns matching `competitor_observations` schema. Used for backfilling historical data (deferred, but the surface exists) or bulk corrections.
- **Recent observations table** — last 100 observations across all sources, sortable, exportable for audit.
- **Per-source observation view** — drill into one source to see all its recent observations and parse-failure logs.
```

## §7.7 CSV Export — new section

Insert as new §7.7:

```markdown
### 7.7 CSV Export

Approved/published prices export to UTF-8 CSV. Trigger via "Export CSV" button in the Daily Review header and in the admin section. Columns:

- merchant_id
- display_name
- online_sell
- in_mail_buy
- in_store_buy
- electronic_buy
- published_at
- risk_status

Empty/null prices render as blank cells. Filename: `zeal_prices_YYYY-MM-DD.csv`.

The export is read-only; clicking the button does not modify any prices or state. Architecture §13 explicitly rules out automated price publishing.
```

## §8 Pricing engine — implementation outline

Replace the existing dataclass and function signature pseudocode with:

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

def compute_prices(
    ebay_sell_pct: float | None,
    ebay_confidence: Literal["high", "medium", "low", "none"],
    competitor: CompetitorAggregate,
    config: MerchantConfig,
    constants: GlobalConstants,
) -> PriceRecommendation:
    ...
```

Remove the long pseudocode body that exists in the current architecture doc; the body implements `pricing_algorithm.md` §5 and the spec is the source of truth.

Replace the current "Test strategy" paragraph with:

```markdown
**Test strategy:** the file `tests/fixtures/spreadsheet_baseline.json` continues to verify the faithful-port property (281 records, ebay_weight = 1.0). A new fixture `tests/fixtures/blending_cases.json` adds hand-computed expectations for representative merchants at ebay_weight ∈ {0.5, 0.7, 0.9} with synthesized competitor data, verifying spec §5 blending math. A third fixture `tests/fixtures/exclusion_cases.json` covers extended validity filter behavior (spec §6.2). All three loop the engine and assert outputs match to within ±0.001.
```

## §9.4 Updates — extension

Append this paragraph to §9.4:

```markdown
When a competitor scraper breaks (source layout change), expect the relevant `competitor_sources.last_attempted_refresh` to update but `last_successful_refresh` to stagnate. The dashboard's Refresh Status competitor panel surfaces this. The fix is a code update + scraper test rerun; not user-actionable.
```

## §10 Backup and recovery

Update the "What to back up" sentence to:

```markdown
**What to back up:** `data/zeal.db` is the only stateful file. Everything else is in git. The database includes merchant config, eBay observations, competitor observations and source config, recommendations, and operator action history.
```

## §11 Build sequence — full revision

Replace the entire existing build sequence with:

```markdown
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
- Engine extended to return ChannelResult with breakdown per spec §5.6
- **Acceptance:** running the daily refresh on one merchant pulls data, computes a recommendation with breakdown, and the dashboard shows it. ebay_weight = 1.0 default; no competitor data yet.

### Phase 3 — Go wide + competitor foundation (week 3)

Goal: all merchants, real dashboard, operator can act on recommendations. Competitor schema and manual-entry path operational.

- Refresh orchestrator handles all active merchants
- Daily Review page with priority sort
- Merchant Detail page with breakdown rendering
- Accept / Override / Skip flows
- HTMX wiring for in-place updates
- Manual "refresh now" button
- Risk flag UI (badge, config edit field, Accept-button gate for paused/no_buy)
- Competitor schema in place — `competitor_sources` and `competitor_observations` tables with migrations
- Manual competitor entry form + CSV import path
- Competitor panel on merchant detail (will show "no data yet" until Phase 4)
- **Acceptance:** operator can run a full eBay refresh, review every merchant, take action on each. Manual competitor entries appear in the dashboard. Blending math is exercised by tests but operationally everything still uses ebay_weight = 1.0 default.

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
- **Acceptance:** operator uses the tool to set prices for one full day independently. CardCash data appears for at least 50 merchants. Operator has tried adjusting ebay_weight on at least one merchant.

### Phase 5 — Raise scraper + post-launch refinement (on demand)

Goal: second competitor source, post-launch fixes.

- Raise scraper integration after CardCash has been running for a week+ without operational issues
- Bug fixes from Phase 4 deploy
- Iteration on operator feedback
```

## §12 Open questions — additions

Append these three questions:

```markdown
- **Q8.** What's the right `competitor_electronic_markdown` value? 0.05 is provisional. Refines as data accumulates.
- **Q9.** CardCash scrape frequency — weekly is the spec default but should be re-evaluated after the first scraper runs. If the source has stricter rate limits than expected, may need to drop to bi-weekly.
- **Q10.** When a competitor scraper fails (source layout change, anti-bot block), should the operator be alerted via a dashboard banner, or is the Refresh Status page sufficient? Default: Refresh Status only; banner if operator finds the page-only version too easy to miss.
```

## §13 Out of scope — additions

Append these four bullets to the existing list:

```markdown
- **Automated competitor source discovery.** New competitor sources are added by code change, not by configuration.
- **Real-time competitor refresh.** Competitor scraping is on a daily-or-slower cadence by design.
- **Competitor data export.** Only Zeal's approved prices export to CSV in v1.
- **Per-channel ebay_weight.** Single weight per merchant applies to all channels uniformly.
```

## §14 Acceptance criteria — full revision

Replace the existing acceptance criteria list with:

```markdown
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
11. Documentation in `docs/` reflects the as-built system
```
