# Audit Report 00 — Executive Summary

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review  
**Auditor:** Claude Opus 4.7 (via claude-sonnet-4-6)  
**Baseline:** 493 tests passing, ruff clean, mypy clean — confirmed before and after audit

---

## Overall Assessment

The codebase is in good health for its current phase. The pure pricing engine is well-tested (281 golden records, 493 total passing tests), the architecture is clean (correct layer separation, no FastAPI/SQLite in pricing, no Browse API anywhere), and the eBay integration is correctly gated behind a config switch that defaults to synthetic. There are no critical bugs, no leaked secrets, no hardcoded credentials, and no broken tests.

The main findings fall into three categories: (1) stale and drifted documentation — most significantly `architecture.md`, which describes a repo layout and features that don't exist yet; (2) minor dead code — an empty placeholder module, one unused Pydantic model class, one stale TODO; and (3) a small set of test coverage gaps, the highest-priority of which protect against silent operator-visible pricing errors.

---

## Recommended Changes

Severity ratings: **low / med / high**  
Risk-of-change ratings: **low / med / high** (higher risk = more test surface, more blast radius)

---

### [docs] Update `architecture.md` §3 repo layout to reflect actual codebase

**Severity: med | Risk: low**

The repo layout in §3 lists ~10 paths that do not exist (`ingestion/competitor/`, `scripts/launch_dashboard.ps1`, `htmx.min.js`, `tests/test_blending.py`, etc.) and omits `merchant_config.html`. §5 describes a CardCash competitor refresh step that is not implemented. §8 pseudocode uses `@dataclass` for types that are Pydantic `BaseModel`. §9.1 and §14 reference commands and acceptance criteria that cannot be met.

No code changes; doc-only updates. The drift is significant enough that a developer or future AI agent reading §3 as a map of the codebase would form a wrong mental model.

---

### [docs] Add cross-references or struck-through notes in `decisions_log.md` for superseded entries

**Severity: low | Risk: low**

The 2026-05-01 entry "eBay Browse API, not scraping eBay" and the 2026-05-01 "Scheduled refresh via Windows Task Scheduler" entries are superseded by later decisions but are not marked. A reader scanning headings could misread the old policy as current. The log is append-only, so add a forward-reference line ("Superseded by 2026-05-05 entry") to the old headings.

---

### [docs] Update eBay status date strings when eBay responds

**Severity: low | Risk: low**

Strings "As of 2026-05-08, eBay has not yet responded" appear in `architecture.md` §12 Q1, `pricing_algorithm.md` §6.1, `decisions_log.md`, and `credential_day_validation_plan.md`. These will become stale once eBay responds. Update at credential-day time, not before.

---

### [dead-code] Remove `src/zeal/jobs/__init__.py`

**Severity: low | Risk: low**

The file is one blank line; nothing imports it; nothing depends on it. Removing it makes the empty "jobs" package disappear cleanly. Risk: zero — no references anywhere.

---

### [dead-code] Remove `EbaySummary` class from `src/zeal/models/ebay.py` (lines 30–37)

**Severity: low | Risk: low**

The class is never instantiated or imported outside its own file. The `ebay_summary` table is written via raw SQL in `refresh.py`. Removing the unused Pydantic model reduces confusion about whether it's part of the data contract.

---

### [dead-code] Evaluate removing `CompetitorSource` class from `src/zeal/models/competitor.py` (lines 11–19)

**Severity: low | Risk: low**

`CompetitorSource` is never instantiated in v1 code. The `competitor_sources` table is seeded by raw SQL. If no future code needs the model, remove it. If the intent is to use it for a future competitor scraper, document that intent in a comment.

---

### [dead-code] Remove stale TODO comment at `src/zeal/web/routes/refresh.py:70`

**Severity: low | Risk: low**

The TODO ("replace SyntheticEbayClient with the real Marketplace Insights client") implies a code change that is not needed. The factory mechanism is already implemented. Replace with a brief comment describing what the factory does, or remove entirely.

---

### [dead-code] Remove or rename garbled artifact directory `c:devzeal-pricing-toolscripts/`

**Severity: low | Risk: low**

Empty directory with a garbled name (path-mangling artifact from a prior session). Cannot be a valid directory name on Windows. Should be removed.

---

### [dead-code] Consolidate `_mode_context()` duplication across three route files

**Severity: low | Risk: low**

The identical 6-line function is defined in `dashboard.py:32`, `merchant.py:147`, and `refresh.py:174`. Move to `web/templating.py` or a shared `web/routes/_shared.py`. If a new context key is ever added, all three files currently need updating. No behavior change, only consolidation.

---

### [dead-code] Extract `_row_to_merchant()` into `db/repositories.py` to eliminate duplication with `cli.py`

**Severity: med | Risk: low**

`ingestion/refresh.py:287–319` and `cli.py:113–157` both map a `sqlite3.Row` to `MerchantRecord`. The `cli.py` version omits `merch_credit_variant` relative to the `refresh.py` version — a divergence that could cause a schema-evolution bug. Extracting a shared function and calling it from both eliminates the silent divergence. Low risk: the function body is well-covered by golden tests.

---

### [ebay] Fix `_invalid_scope_message()` to reference `_SCOPE` constant instead of repeating the literal

**Severity: low | Risk: low**

`ebay_oauth.py:95` repeats `"https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"` instead of referencing the module constant `_SCOPE` defined at line 11. If the scope string ever changes, both places require updating. One-line fix.

---

### [ebay] Consider making `per_call_sleep_ms` configurable via env var

**Severity: low | Risk: low**

`EbayMarketplaceInsightsClient.__init__` defaults `per_call_sleep_ms=100`. This default is hardcoded; if the granted eBay tier needs different pacing, a code change is required. Adding a `EBAY_SLEEP_MS` env var read in `config.py` and threading it through `create_ebay_client()` would make it config-only. Non-urgent: only relevant after live access is granted and quota is measured.

---

### [security] Confirm HTMX is bundled locally before any future networked deployment

**Severity: low (for v1 local) | Risk: low**

`base.html` loads HTMX via CDN (`https://unpkg.com/htmx.org`). For the current localhost-only deployment this is acceptable. If the dashboard is ever exposed to a network, bundle `htmx.min.js` as a static file (as the `architecture.md` layout already anticipates). Not an action item for v1.

---

### [tests] Add direct test for synthetic-mode 409 at `POST /refresh`

**Severity: med | Risk: low**

`web/routes/refresh.py:95–99` returns 409 when `ebay_mode == "synthetic"`. This path is not covered by any test in `test_refresh_routes.py`. If the guard is accidentally removed, live refresh could be triggered in synthetic mode, writing garbage recommendations. One new test, no production code change.

---

### [tests] Add direct test for `fetch_pricing_list_summary()` aggregation

**Severity: med | Risk: low**

`repositories.py:181` computes `no_data`, `with_recommendation`, and `live_ebay_observations` counts. These are surfaced on the dashboard. No test verifies the SQL counts directly. A wrong count would be operator-visible but hard to catch via route tests alone.

---

### [tests] Add direct test for `_persist_observations()` ON CONFLICT upsert

**Severity: med | Risk: low**

`refresh.py:200–237` upserts `ebay_observations` on `listing_id` conflict. No test verifies that a duplicate `listing_id` updates the existing row rather than failing or inserting a duplicate. Schema constraint prevents duplicate rows, but the updated field values after upsert are untested.

---

### [tests] Add direct test for `_parse_percent()` fraction-input guard

**Severity: high | Risk: low**

`merchant.py:427–429`: if the operator enters `0.85` (a fraction) instead of `85`, the field is rejected with an error message. This path exists specifically to prevent a silent pricing error (storing `0.0085` when `0.85` was intended). If the guard regresses, an operator entering a fraction could silently corrupt a merchant's margin. One new test, no production code change.

---

## Do Not Touch in This Audit

The following are explicitly out of scope for the audit phase and must not be modified:

- **Pricing algorithm** (`src/zeal/pricing/engine.py`, `blending.py`, `confidence.py`, `ebay_average.py`, `listing_filter.py`): any change risks golden-test regression and algorithm drift from the spec.
- **DB schema** (`src/zeal/db/schema.sql`): schema changes require migrations and a deliberate decision.
- **Refresh behavior** (`ingestion/refresh.py`): the run-refresh loop, override logic, and per-merchant error handling are sensitive; changes require end-to-end validation.
- **`.env`**: no credential or mode changes during the audit.
- **Live eBay behavior**: any change to `ebay_oauth.py`, `ebay_marketplace_insights_client.py`, or `ebay_client_factory.py` must not alter live API behavior while production Marketplace Insights entitlement is blocked.
- **Golden test tolerance** (`test_pricing_engine_baseline.py`): `±0.001` tolerance is spec-defined. Do not tighten or loosen.
- **Any feature introduction**: no new routes, templates, DB columns, or UI surfaces.
