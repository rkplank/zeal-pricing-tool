# Open Items — Post-Audit Triage

**Created:** 2026-05-10  
**Branch:** audit/opus-4-7-review  
**Source:** Consolidated from `10_bugs_to_review.md`, `11_followups.md`, and `08_proposed_deletions.md`

This is the single triage list for everything not resolved in Phases 1–5.
Close each item by resolving it in a follow-up PR and marking it Done here.

Items are grouped by urgency. Within a group, order is priority.

---

## 🔴 High — address before first real operator demo

### OI-1: `_parse_percent()` fraction-input guard not directly tested

**Risk if unaddressed:** Operator enters `0.85` meaning 85%; guard (which exists and works) blocks it and shows an error. If guard ever regresses, `0.85` would be silently stored as `0.0085`, corrupting the merchant margin. Config editor could corrupt live pricing.

**File:line:** `src/zeal/web/routes/merchant.py:427-429`

```python
if 0 < percent <= 1:
    errors[field] = "Enter human percentages like 85 or 85%, not fractions like 0.85."
    return None
```

**Fix:** Add a test in `test_web_routes.py` (or `test_merchant_config_invalid_percentage_is_rejected`) that POSTs `"in_store_margin": "0.85"` and asserts 400 with an error message containing "fractions".

**Effort:** ~30 min, test-only, no production code change.

---

## 🟡 Medium — address before full live eBay refresh

### OI-2: `POST /refresh` synthetic-mode 409 guard not tested

**Risk if unaddressed:** If the guard at `refresh.py:95-99` is accidentally removed, a live refresh could be triggered from a synthetic-mode dashboard, producing garbage recommendations or hitting live eBay with synthetic merchant data.

**File:line:** `src/zeal/web/routes/refresh.py:95-99`

**Fix:** Add a test in `test_refresh_routes.py` that creates an app with `ebay_mode="synthetic"` and POSTs to `/refresh`, asserting status 409 and the body "Refresh is disabled in synthetic mode".

**Effort:** ~20 min, test-only.

---

### OI-3: `fetch_pricing_list_summary()` SQL aggregation not directly tested

**Risk if unaddressed:** Wrong `no_data`, `with_recommendation`, or `live_ebay_observations` counts displayed in the dashboard header. Operator could be misled about the state of their data.

**File:line:** `src/zeal/db/repositories.py:181`

**Fix:** Add a test in `test_repositories.py` that seeds 3 merchants with known recommendation states and asserts the exact summary values.

**Effort:** ~45 min, test-only.

---

### OI-4: `_persist_observations()` ON CONFLICT upsert not isolated

**Risk if unaddressed:** If the upsert behavior changes (e.g., due to an SQLite version difference), duplicate listing_id rows could corrupt `ebay_observations`. Currently the schema constraint prevents duplicates but the updated field values are unverified.

**File:line:** `src/zeal/ingestion/refresh.py:200`

**Fix:** Add a test (via `run_refresh()` with a `SyntheticEbayClient` returning the same listing twice with different field values) that asserts the second set of values overwrites the first.

**Effort:** ~45 min, test-only.

---

### OI-5: `_row_to_merchant()` duplicated between `refresh.py` and `cli.py`

**Risk if unaddressed:** If a schema column is added to `merchants`, both row-mapping functions must be updated. A missed update in either could produce a `MerchantRecord` with a stale default value.

**File:line:**
- `src/zeal/ingestion/refresh.py:287-319` (`_row_to_merchant`)
- `src/zeal/cli.py:113-157` (`_load_merchant`)

**Fix:** Extract `_row_to_merchant()` from `refresh.py` into `src/zeal/db/repositories.py` as a public function. Call it from both `refresh.py` and `cli.py`. No circular import: `cli.py` already imports from `db.connection`; adding `db.repositories` is clean.

**Effort:** ~1 hr, touches 3 files, low behavioral risk.

---

## 🟢 Low — address when convenient or triggered by another event

### OI-6: `src/zeal/jobs/__init__.py` — empty file deletion

**Status:** Awaiting approval (see `08_proposed_deletions.md`).

**Decision needed:** Approve deletion of the file (zero risk, zero references). The `jobs/` directory also disappears.

**If approved:** `git rm src/zeal/jobs/__init__.py`, confirm `jobs/` is gone, run tests.

---

### OI-7: Garbled artifact directory `c:devzeal-pricing-toolscripts/`

**Status:** Awaiting approval (see `08_proposed_deletions.md`).

**Decision needed:** Approve deletion of the empty garbled directory. Requires a shell `rmdir` or equivalent; cannot be done via git alone.

**If approved:** `Remove-Item -Recurse "c:devzeal-pricing-toolscripts"` (PowerShell), confirm gone.

---

### OI-8: `CompetitorSource` class in `src/zeal/models/competitor.py` — possibly unused

**Context:** The class is never instantiated in v1. The `competitor_sources` table is populated via raw SQL in `db/seed.py`. `CompetitorObservation` (the sibling class) IS used. `CompetitorSource` may be the intended Pydantic model for the v2 CardCash scraper's data contract.

**Decision needed:** Keep as the future scraper's model definition (add a comment documenting its intended role), or remove now and re-add when the scraper is built.

**File:line:** `src/zeal/models/competitor.py:11-19`

---

### OI-9: `per_call_sleep_ms` not configurable via env var

**Context:** `EbayMarketplaceInsightsClient.__init__` defaults `per_call_sleep_ms=100`. This is not exposed in `ZealConfig`. If the eBay tier granted has different quota needs, a code change is required.

**Timing:** Only actionable after credential day and quota measurement.

**File:line:** `src/zeal/ingestion/ebay_marketplace_insights_client.py:103`, `src/zeal/ingestion/ebay_client_factory.py:14`

**Fix:** Add `EBAY_SLEEP_MS` int env var to `ZealConfig`, pass as `per_call_sleep_ms` in `create_ebay_client()`.

---

### OI-10: HTMX loaded via CDN; should be bundled before networked deployment

**Context:** `src/zeal/web/templates/base.html` loads HTMX from `https://unpkg.com/htmx.org`. Acceptable for v1 localhost-only. If the dashboard is ever served to a network, bundle `htmx.min.js` as a static file (the `architecture.md` layout anticipates this as `web/static/htmx.min.js`).

**Timing:** Not needed until networked deployment is planned.

---

### OI-11: `type: ignore[operator]` in `web/routes/refresh.py:71` — untyped `app.state`

**Context:** FastAPI's `State` is untyped; `ebay_client_factory` is stored as `object`. The suppression is correct and narrow. Fixing requires a typed `AppState` wrapper class or a `cast()`, touching `app.py` and multiple tests.

**Timing:** v2 cleanup sprint.

**File:line:** `src/zeal/web/routes/refresh.py:71`

---

## Closed items (resolved in this audit)

| ID | Item | Resolved in |
|---|---|---|
| — | `EbaySummary` unused class removed | Phase 3 |
| — | `_invalid_scope_message()` scope literal de-duplicated | Phase 3 |
| — | `_mode_context()` triplication consolidated into `web/templating.py` | Phase 3 |
| — | Stale TODO in `refresh.py:70` replaced with accurate comment | Phase 3 |
| — | All `architecture.md` phantom paths corrected | Phase 2 |
| — | All agent-facing docs (CLAUDE.md, AGENTS.md) eBay status updated | Phase 2 |
| — | All other docs aligned with current scope and code state | Phase 2 |
| — | `credential_day_runbook.md` written; 35-item readiness checklist all PASS | Phase 4 |
| — | `print()` in `cli.py` reviewed — intentional, no action | Phase 3 |
| — | All `except Exception:` handlers reviewed — correctly broad, no action | Phase 3 |
