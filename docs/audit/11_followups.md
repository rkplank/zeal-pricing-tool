# Audit Report 11 — Follow-Ups and Deferred Items

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

Items deferred from Phase 3 cleanup: either out of Phase 3 scope, require human
decision, or carry medium/high risk for this phase.

---

## #1 — `CompetitorSource` class in `models/competitor.py` (possibly unused)

**File:line:** `src/zeal/models/competitor.py:11-19`

**Finding from audit 02:** The class is never instantiated in v1. `competitor_sources`
DB inserts in `db/seed.py` use raw SQL, not the Pydantic model. Search confirmed
no import outside the definition file.

**Why deferred:** Audit 02 classified this as "possibly unused — needs human eyes."
Unlike `EbaySummary` (which had zero live use cases), `CompetitorSource` exists
alongside `CompetitorObservation` as part of the competitor data layer. If the
planned CardCash scraper (v2) uses this model, deleting it now would require
re-adding it. Decision: leave in place and re-evaluate when the scraper is built.

**Action:** Confirm with operator/developer whether `CompetitorSource` Pydantic
model is intended to be the data contract for competitor source configuration,
or whether it can be dropped and raw SQL / dict used instead.

---

## #2 — `print()` calls in `src/zeal/cli.py` (intentional, no action needed)

**File:line:** `src/zeal/cli.py:26, 37, 59, 63, 67, 83, 91-96, 102-107, 109`

**Finding from audit 04:** All `print()` calls are in the CLI module. Phase 3
instruction says to replace with logging, but audit 04 correctly identified these
as intentional: `cli.py` is an operator-facing terminal tool where `print()` to
stdout is the correct output mechanism. `logging` routes to stderr/log files
and is not appropriate for terminal tool output.

**Resolution:** No action taken. `print()` in `cli.py` is acceptable and correct.
This item is closed.

---

## #3 — `_row_to_merchant()` duplication between `refresh.py` and `cli.py`

Cross-referenced with `10_bugs_to_review.md` BUG-01. Extract to
`db/repositories.py` in a dedicated PR. Not done in Phase 3 because it touches
three files simultaneously (not "clearly local").

---

## #4 — `type: ignore[operator]` suppression in `web/routes/refresh.py:71`

Cross-referenced with `10_bugs_to_review.md` BUG-02. Requires typed `app.state`
or a custom `FastAPI` subclass. Leave for v2 cleanup.

---

## #5 — Template filter labels for competitor channels (`buy_mail`, `buy_electronic`, `marketplace_sell`)

**File:line:** `src/zeal/web/templating.py:66-77`

**Finding from audit 02:** `_format_channel` includes labels for competitor channel
values. These are only reached via the competitor panel template when competitor
observations exist. In synthetic mode with no competitor data, they are dead
letters. Once the CardCash scraper is built and observations are populated, they
will be exercised.

**Action:** No change needed. Labels are correct for when data exists.

---

## #6 — `MerchantListRow.has_live_ebay_observations` always 0 in synthetic mode

**File:line:** `src/zeal/db/repositories.py:490`

**Finding from audit 02:** The `live_ebay_observations` count in the dashboard
header is always 0 in synthetic mode. This is expected behavior, not a bug.
The count will be non-zero only after a successful live eBay refresh.

**Action:** None. No test change needed. The template correctly shows 0 in
synthetic mode.

---

## #7 — `_parse_percent()` fraction-input guard coverage gap

Cross-referenced with `10_bugs_to_review.md` BUG-05. Add a direct test in
Phase 4. High priority.

---

## #8 — `POST /refresh` synthetic-mode 409 not tested

Cross-referenced with `10_bugs_to_review.md` BUG-06. Add in Phase 4.

---

## #9 — HTMX loaded via CDN in `base.html`

**File:line:** `src/zeal/web/templates/base.html`

**Finding from audit 06:** HTMX is loaded via `https://unpkg.com/htmx.org` rather
than a local static file. For the current localhost-only deployment this is
acceptable (requires internet access; no offline use case today). The
`architecture.md` originally listed `htmx.min.js` as a static file — this is
now corrected in the docs.

**Action when relevant:** Bundle `htmx.min.js` as `web/static/htmx.min.js`
before any future networked deployment. Not needed for v1.

---

## #10 — `per_call_sleep_ms` not configurable via env var

**File:line:** `src/zeal/ingestion/ebay_marketplace_insights_client.py:103`

**Finding from audit 05:** `per_call_sleep_ms=100` is hardcoded as default and not
exposed in `ZealConfig`. If the granted eBay tier needs different pacing, a code
change would be required.

**Action when relevant:** After credential-day validation and quota measurement,
consider adding `EBAY_SLEEP_MS` env var in `config.py` and threading it through
`create_ebay_client()`. Not needed until live pacing is observed.
