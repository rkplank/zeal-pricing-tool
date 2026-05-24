# Audit Report 01 — Repository Inventory

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review  
**Commit:** 1d31eb0

---

## 1. `src/zeal/` tree (3 levels)

```
src/zeal/
├── __init__.py                        # package marker; empty
├── cli.py                             # CLI entry point: init-db, seed, seed-demo, serve, smoke-ebay
├── config.py                          # ZealConfig dataclass; reads ZEAL_EBAY_MODE, EBAY_* from env
├── db/
│   ├── __init__.py                    # package marker; empty
│   ├── connection.py                  # SQLite connection helper; apply_schema(); DEFAULT_DB_PATH
│   ├── repositories.py                # all DB read/write functions; dataclasses for query results
│   └── seed.py                        # seeds baseline fixture and synthetic recommendations into SQLite
├── ingestion/
│   ├── __init__.py                    # package marker; empty
│   ├── ebay_client.py                 # EbayClient Protocol + SyntheticEbayClient (no-network test double)
│   ├── ebay_client_factory.py         # create_ebay_client(): returns synthetic or live client by config
│   ├── ebay_errors.py                 # typed exception hierarchy for eBay error cases
│   ├── ebay_marketplace_insights_client.py  # live EbayMarketplaceInsightsClient; OAuth + pagination + retry
│   ├── ebay_oauth.py                  # EbayTokenManager; fetches/caches OAuth2 app token from eBay
│   └── refresh.py                     # run_refresh() orchestrator; per-merchant eBay fetch → price rec loop
├── jobs/
│   └── __init__.py                    # EMPTY placeholder; no v1 scheduled-job code
├── models/
│   ├── __init__.py                    # package marker; empty
│   ├── competitor.py                  # CompetitorSource and CompetitorObservation Pydantic models
│   ├── ebay.py                        # EbaySoldListing, EbayObservation, EbaySummary Pydantic models
│   ├── merchant.py                    # MerchantConfig and MerchantRecord Pydantic models
│   └── pricing.py                     # GlobalConstants, CompetitorAggregate, PriceRecommendation, BreakdownStep
├── pricing/
│   ├── __init__.py                    # package marker; empty
│   ├── blending.py                    # blend_values(): weighted eBay/competitor blend (pure)
│   ├── competitor_aggregate.py        # aggregate_competitor_observations(): weighted average per channel (pure)
│   ├── confidence.py                  # score_confidence(): maps sample_size + age_days → confidence label (pure)
│   ├── ebay_average.py               # compute_ebay_average(): mean sale_price/face_value across observations (pure)
│   ├── engine.py                      # compute_prices(): four-channel pricing formulas; the core algorithm (pure)
│   └── listing_filter.py             # filter_listings(): validity, regex, face-value, date filters (pure)
└── web/
    ├── __init__.py                    # package marker; empty
    ├── app.py                         # create_app(): FastAPI app factory; lifespan wiring; router includes
    ├── routes/
    │   ├── __init__.py               # package marker; empty
    │   ├── dashboard.py              # GET / — pricing list view
    │   ├── merchant.py               # GET /merchant/{id}, GET/POST /merchant/{id}/config; chart helpers
    │   └── refresh.py               # POST /refresh, GET /refresh/status; background refresh task dispatcher
    ├── static/
    │   └── style.css                 # all dashboard CSS; no external CSS framework
    └── templates/
        ├── base.html                 # shared layout: nav, status strip, HTMX CDN link
        ├── dashboard.html            # pricing list table
        ├── merchant_config.html      # merchant config edit form
        ├── merchant_detail.html      # merchant detail: recommendation cards, chart, breakdown, observations
        └── partials/
            ├── breakdown.html        # formula breakdown partial (HTMX target)
            ├── competitor_panel.html # competitor reference panel partial
            ├── refresh_idle.html     # refresh button / last-completed status (HTMX swap target)
            └── refresh_running.html  # progress bar during active refresh (HTMX swap target)
```

---

## 2. Per-module purpose

| Module | Purpose |
|---|---|
| `__init__.py` files (6) | Package markers; all empty |
| `cli.py` | Typer-free argparse CLI with five subcommands; also the `smoke-ebay` operator diagnostic |
| `config.py` | Single env-read point; validates and returns `ZealConfig`; no global state |
| `db/connection.py` | SQLite connection with foreign keys + Row factory; schema loader |
| `db/repositories.py` | All query/mutation functions; typed result dataclasses; no business logic |
| `db/seed.py` | One-shot seeder; reads baseline JSON fixture, calls engine, inserts synthetic recs |
| `ingestion/ebay_client.py` | `EbayClient` Protocol (structural) + `SyntheticEbayClient` test double |
| `ingestion/ebay_client_factory.py` | Thin factory that reads config and returns the right `EbayClient` implementation |
| `ingestion/ebay_errors.py` | Exception types: `EbayAuthError`, `EbayRateLimitError`, `EbayServerError`, `EbayNetworkError` |
| `ingestion/ebay_marketplace_insights_client.py` | Live eBay client: OAuth, pagination, retry, face-value heuristic, `_parse_item` |
| `ingestion/ebay_oauth.py` | `EbayTokenManager`: client-credentials OAuth flow with per-instance token cache |
| `ingestion/refresh.py` | `run_refresh()`: iterates active merchants, calls eBay client, writes observations + recs |
| `jobs/__init__.py` | **Empty placeholder** — no code, no imports; v1 has no scheduled jobs |
| `models/competitor.py` | `CompetitorSource` and `CompetitorObservation` Pydantic models |
| `models/ebay.py` | `EbaySoldListing`, `EbayObservation`, `EbaySummary` Pydantic models |
| `models/merchant.py` | `MerchantConfig` + `MerchantRecord` Pydantic models; shared across layers |
| `models/pricing.py` | `GlobalConstants`, `CompetitorAggregate`, `ChannelResult`, `PriceRecommendation`, `BreakdownStep` |
| `pricing/blending.py` | `blend_values()`: weighted average of eBay and competitor values |
| `pricing/competitor_aggregate.py` | `aggregate_competitor_observations()`: source/channel dedup + confidence-weighted average |
| `pricing/confidence.py` | `score_confidence()`: maps sample size + recency to `high/medium/low/none` |
| `pricing/ebay_average.py` | `compute_ebay_average()`: mean sell % from `EbayObservation` list |
| `pricing/engine.py` | `compute_prices()`: four-channel algorithm; calls blending if competitor data present |
| `pricing/listing_filter.py` | `filter_listings()`: excludes listings by regex, face-value, recency, partial keywords |
| `web/app.py` | FastAPI factory; lifespan hooks (interrupt cleanup, config load, HTTP client, eBay factory) |
| `web/routes/dashboard.py` | `GET /` route handler; fetches pricing list + summary; renders `dashboard.html` |
| `web/routes/merchant.py` | `GET /merchant/{id}`, config form GET/POST; chart builders; percent parsing helpers |
| `web/routes/refresh.py` | Refresh POST/GET routes; background task dispatcher; progress polling |
| `web/templating.py` | Jinja2 env setup; all custom template filters (`pct`, `pp`, `channel`, `datetime`, etc.) |

---

## 3. Dead-code / import isolation candidates

### `src/zeal/jobs/__init__.py`
- **Imports nothing from the package.** Nothing in the package imports it.
- File is 1 line (a blank line) per `Read` tool.
- Confirmed dead: `grep -r "zeal.jobs" src/ tests/` returns no matches.
- Candidate for removal.

### `src/zeal/models/competitor.py` — `CompetitorSource` class
- `CompetitorObservation` is actively used (`pricing/competitor_aggregate.py`, `db/repositories.py`, tests).
- `CompetitorSource` model class: only usage is in `db/seed.py` which does a raw SQL `INSERT` without instantiating the Pydantic model.
- Search: `grep -rn "CompetitorSource" src/ tests/` — zero uses outside the model file itself and `db/seed.py` (which references only the table, not the class).
- Status: **possibly unused as Pydantic model**; the DB schema has a `competitor_sources` table and the seed inserts a row, but the class is never instantiated. Needs human confirmation that no future code path instantiates it.

### `src/zeal/models/ebay.py` — `EbaySummary` class
- `EbaySoldListing` and `EbayObservation` are actively used.
- `EbaySummary`: search `grep -rn "EbaySummary" src/ tests/` — no import or instantiation found in src or tests.
- Status: **possibly unused**; defined but no code constructs or passes it anywhere in v1.

---

## 4. Root-level file classification

| Path | Classification | Reason |
|---|---|---|
| `README.md` | keep | Project overview; accurate and current |
| `CLAUDE.md` | keep | Claude Code instructions; authoritative |
| `AGENTS.md` | keep | Codex instructions; authoritative |
| `pyproject.toml` | keep | Build config |
| `uv.lock` | keep | Lockfile |
| `.python-version` | keep | Python version pin |
| `.env` | keep | Runtime secrets; gitignored; not staged |
| `.env.example` | keep | Template for credential-day setup |
| `.gitignore` | keep | Standard |
| `zeal_pricing_handoff_after_codex_prompt6.md` | **unsure / candidate-removal** | Handoff doc from a prior session; not referenced by any source file or doc; appears to be a one-time artifact; unclear if it contains any information not captured elsewhere in `docs/` |
| `c:devzeal-pricing-toolscripts/` | **candidate-removal** | Garbled artifact directory created by a prior session misinterpreting a Windows path as a Unix path in Bash; appears empty; not a valid directory name on Windows; has no purpose |
