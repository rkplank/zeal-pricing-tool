# Audit Report 00 — Executive Summary

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review  
**Auditor:** Claude Opus 4.7 (via claude-sonnet-4-6)  
**Baseline:** 493 tests passing, ruff clean, mypy clean — confirmed before and after every phase

---

## Overall Assessment

The codebase is in good health for its current phase. The pure pricing engine is well-tested (281 golden records, 493 total passing tests), the architecture is clean (correct layer separation, no FastAPI/SQLite in pricing, no Browse API anywhere), and the eBay integration is correctly gated behind a config switch that defaults to synthetic. There are no critical bugs, no leaked secrets, no hardcoded credentials, and no broken tests.

The main findings fell into three categories: (1) stale and drifted documentation — most significantly `architecture.md`, which described a repo layout and features that do not yet exist; (2) minor dead code — an empty placeholder module, one unused Pydantic model class, one stale TODO; and (3) a small set of test coverage gaps, the highest-priority of which protect against silent operator-visible pricing errors.

All Phase 1–4 audit work is complete. Phases 2–3 made targeted fixes. Phase 4 confirmed the credential-day path is config-only. Phase 5 consolidates findings for review.

---

## Findings and Status

Severity: **low / med / high**. Risk-of-change: **low / med / high**.

| # | Tag | Finding | Severity | Risk | Status |
|---|---|---|---|---|---|
| 1 | [docs] | `architecture.md` §3 repo layout had ~10 phantom paths; §5 described CardCash refresh not built; §8 pseudocode used `@dataclass` not Pydantic; §9.1 referenced non-existent commands; §14 had unmet acceptance criteria | med | low | ✅ **Done — Phase 2** |
| 2 | [docs] | `decisions_log.md` headings for superseded "eBay Browse API" and "Scheduled refresh" entries had no cross-reference to superseding entries | low | low | ✅ **Done — Phase 2** (new entries added; append-only rule preserved) |
| 3 | [docs] | "As of 2026-05-08" eBay status strings stale across multiple docs | low | low | ✅ **Done — Phase 2** (updated to 2026-05-10 with verbatim status language) |
| 4 | [docs] | `pricing_algorithm.md` §1 described CardCash scraper as current; §7 described it as implemented; §6.5 said regex editing was v2 work | med | low | ✅ **Done — Phase 2** |
| 5 | [docs] | `operator_demo_script.md` and `dashboard_usability_review_plan.md` had wrong merchant detail section order and stale Browse API prohibition phrasing | low | low | ✅ **Done — Phase 2** |
| 6 | [docs] | `README.md` lacked "what the dashboard does NOT show" section; eBay status unclear | med | low | ✅ **Done — Phase 2** |
| 7 | [docs] | `historical_pricing_findings.md`, `historical_pricing_analysis.md`, `spreadsheet_recon.md` had no header distinguishing them from live specs | low | low | ✅ **Done — Phase 2** (one-line historical header added) |
| 8 | [docs] | `AGENTS.md` and `CLAUDE.md` had stale phase status and stale eBay status | low | low | ✅ **Done — Phase 2** |
| 9 | [docs] | Four new `decisions_log.md` entries missing: price history chart, "saved recommendations not published prices," CardCash scraper not yet built, eBay-access status note | low | low | ✅ **Done — Phase 2** |
| 10 | [docs] | Credential day runbook did not exist as a standalone copy-paste-ready doc | med | low | ✅ **Done — Phase 4** (`docs/credential_day_runbook.md` written) |
| 11 | [dead-code] | `EbaySummary` class in `src/zeal/models/ebay.py` — never instantiated or imported | low | low | ✅ **Done — Phase 3** (class removed; 493 tests still pass) |
| 12 | [dead-code] | Stale TODO comment in `src/zeal/web/routes/refresh.py:70` implied a code change that was already complete | low | low | ✅ **Done — Phase 3** (replaced with accurate comment) |
| 13 | [dead-code] | `_mode_context()` defined identically in three route files | low | low | ✅ **Done — Phase 3** (consolidated into `web/templating.py:mode_context()`) |
| 14 | [ebay] | `_invalid_scope_message()` re-stated the scope string literal instead of referencing `_SCOPE` constant | low | low | ✅ **Done — Phase 3** (`_SCOPE` constant referenced; confirmed in Phase 4 re-verification) |
| 15 | [dead-code] | `src/zeal/jobs/__init__.py` — empty placeholder; nothing imports it | low | low | ⏳ **Awaiting approval** — listed in `08_proposed_deletions.md` |
| 16 | [dead-code] | Garbled artifact directory `c:devzeal-pricing-toolscripts/` — empty, no valid name | low | low | ⏳ **Awaiting approval** — listed in `08_proposed_deletions.md` |
| 17 | [dead-code] | `CompetitorSource` class in `src/zeal/models/competitor.py` — possibly unused (Pydantic model never instantiated in v1) | low | low | ⏳ **Open** — "possibly unused"; deferred until CardCash scraper is designed; see `OPEN_ITEMS.md` #1 |
| 18 | [dead-code] | `_row_to_merchant()` duplicated between `ingestion/refresh.py` and `cli.py` | med | low | ⏳ **Open** — `OPEN_ITEMS.md` #2 |
| 19 | [ebay] | `per_call_sleep_ms=100` hardcoded; not configurable via env var | low | low | ⏳ **Open** — only relevant post credential-day; `OPEN_ITEMS.md` #3 |
| 20 | [security] | HTMX loaded via CDN; should be bundled for any future networked deployment | low | low | ⏳ **Open** — acceptable for v1 localhost; `OPEN_ITEMS.md` #4 |
| 21 | [tests] | `POST /refresh` synthetic-mode 409 guard not directly tested | med | low | ⏳ **Open** — `OPEN_ITEMS.md` #5 |
| 22 | [tests] | `fetch_pricing_list_summary()` SQL aggregation not directly tested | med | low | ⏳ **Open** — `OPEN_ITEMS.md` #6 |
| 23 | [tests] | `_persist_observations()` ON CONFLICT upsert not isolated | med | low | ⏳ **Open** — `OPEN_ITEMS.md` #7 |
| 24 | [tests] | `_parse_percent()` fraction-input guard (`0.85` rejection) not directly tested — **HIGH SEVERITY** | high | low | ⏳ **Open** — `OPEN_ITEMS.md` #8 |
| 25 | [ebay] | eBay credential-day path confirmed config-only; 35-item readiness checklist all PASS | — | — | ✅ **Done — Phase 4** (see `13_ebay_readiness_checklist.md`) |

---

## Completed / Not Applicable

| Item | Outcome |
|---|---|
| Browse API fallback — confirmed absent | No action needed |
| Synthetic mode cannot accidentally hit live endpoints | No action needed |
| All `except Exception:` handlers — correctly broad and logged | No action needed |
| `print()` in `cli.py` — intentional CLI stdout | No action needed |
| Secrets / credentials — none hardcoded, `.env` gitignored | No action needed |
| All pricing algorithm, DB schema, refresh behavior — untouched | Per audit scope |

---

## Do Not Touch (unchanged from Phase 1)

- **Pricing algorithm** (`src/zeal/pricing/engine.py`, `blending.py`, `confidence.py`, `ebay_average.py`, `listing_filter.py`)
- **DB schema** (`src/zeal/db/schema.sql`)
- **Refresh behavior** (`ingestion/refresh.py` loop and error handling)
- **`.env`**
- **Live eBay OAuth scope or endpoint behavior**
- **Golden test tolerance** (`±0.001`)
- **Any feature introduction**

---

## Open Items Summary

See `docs/audit/OPEN_ITEMS.md` for the full triage list. Priority order:

1. **`_parse_percent()` fraction-input guard test** — HIGH severity; silent pricing error risk if guard regresses. Add test before first real operator demo.
2. **`POST /refresh` synthetic-mode 409 test** — med; adds coverage for a live-run guard.
3. **`fetch_pricing_list_summary()` aggregation test** — med; operator-visible counts currently unverified.
4. **`_persist_observations()` upsert test** — med; DB integrity guard.
5. **`_row_to_merchant()` extraction** — low/med; maintenance refactor.
6. **`jobs/__init__.py` deletion** — awaiting approval from `08_proposed_deletions.md`.
7. **`per_call_sleep_ms` env var** — post-credential-day only.
8. **HTMX CDN bundling** — pre-networked-deployment only.
