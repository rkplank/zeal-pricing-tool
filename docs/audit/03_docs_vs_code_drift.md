# Audit Report 03 — Docs vs. Code Drift

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

Each finding cites the doc file, line number(s), and the contradiction or staleness. No files are edited in this phase.

---

## README.md

**Assessment:** Largely accurate. The "Credential-Day Procedure" section correctly references `uv run python -m zeal.cli smoke-ebay`, and the scope section correctly lists what is out of scope. Minor drift:

- **Line 43:** `uv run python -m zeal.cli smoke-ebay --merchant home_depot` — correct, but `smoke-ebay` is not listed in `README.md §Project Structure` script table. The smoke-ebay command is buried only in the credential-day procedure; a reader scanning the README may not know it exists.
- **Line 89:** `jobs/` is described as "placeholder; v1 has no scheduled jobs" — accurate and consistent with code.

No blocking drift. README is in good shape.

---

## AGENTS.md

**Assessment:** Well-maintained. Correctly identifies the production Marketplace Insights block, the narrow merchant config editor scope, and all out-of-scope items. One issue:

- **Lines 79, 83, 85:** These `ebay_weight` UI / competitor blending / recency items are listed as "do not add" — consistent with code.
- **Line 122 (`rg "fastapi" src/zeal/ingestion/`):** The directory-specific `AGENTS.md` in `src/zeal/ingestion/AGENTS.md` also exists (not listed in AGENTS.md at root); not a contradiction, just undocumented at the root level.

No blocking drift.

---

## CLAUDE.md

**Assessment:** Accurate and up to date. The "Current phase and status" section (updated 2026-05-09) correctly reflects the synthetic-mode operating state, eBay block, and narrow config editor implementation.

- No contradictions with code found.
- The status commit hash `c9fe166c0ffb42db08a56208d5b3bf5b9e4ae602` matches the git log (5 commits before HEAD). Minor: the "latest verified commit" note could cause confusion if the reader uses it to check out an older state. Not a code drift issue.

---

## docs/architecture.md

This document has **significant drift** from the actual codebase. Many paths in the §3 repo layout do not exist, and §5 and §14 describe features not yet built.

### §3 — Repository layout (lines 59–136): stale/phantom paths

| Path in doc | Actual state |
|---|---|
| `ingestion/competitor/` | Does **not exist** — no CardCash scraper directory |
| `ingestion/competitor/__init__.py` | Does not exist |
| `ingestion/competitor/base.py` | Does not exist |
| `ingestion/competitor/cardcash.py` | Does not exist |
| `ingestion/competitor/refresh.py` | Does not exist |
| `web/templates/partials/refresh_progress.html` | Does not exist; actual file is `refresh_running.html` |
| `web/static/htmx.min.js` | Does not exist; HTMX is loaded via CDN in `base.html` |
| `tests/test_blending.py` | Does not exist; actual file is `test_pricing_blending.py` |
| `tests/test_parser.py` | Does not exist; actual file is `test_spreadsheet_parser.py` |
| `tests/fixtures/blending_cases.json` | Does not exist |
| `tests/fixtures/exclusion_cases.json` | Does not exist |
| `scripts/launch_dashboard.ps1` | Does not exist (scripts/ has only `extract_baseline.py`, `historical_spreadsheet_recon.py`, `spreadsheet_parser.py`) |
| `scripts/seed_from_spreadsheet.py` | Does not exist under that name |
| `cli.py` comment `# zeal serve, zeal refresh, zeal seed, zeal init-db` | `zeal refresh` command does not exist in `cli.py`; it is not a CLI subcommand |
| `web/templates/merchant_config.html` | Exists — not in the layout tree (omitted from doc) |

### §5 — Refresh data flow (lines 196–214): step 4 is unimplemented

- **Line 206–208:** "Separately, the task also refreshes competitor data (CardCash) for the active merchants. Competitor refresh runs after eBay is complete..." — This step **does not exist** in the current `refresh.py`. `run_refresh()` only iterates eBay; no competitor refresh is called.
- **Lines 210–211:** "~300 merchants x ~3 paginated requests each is ~900 calls per refresh" — the CardCash rate-limit note describes a feature not yet built.

### §8 — Pricing engine pseudocode (lines 456–520)

- Lines 461–480 show `@dataclass(frozen=True)` for `MerchantConfig`, `CompetitorAggregate`, `BreakdownStep`, `ChannelResult`, `PriceRecommendation`, `GlobalConstants` — the actual implementations are **Pydantic `BaseModel`** subclasses, not dataclasses. The pseudocode is illustrative intent, but the types and decorators are wrong. Could mislead a developer who copies from it.
- `GlobalConstants` in the pseudocode (line 503) omits several fields present in the actual model (`ebay_sale_costs`, `ebay_postage_costs`, `online_sell_bonus_competitive`, `online_sell_bonus_zen_nocomp`, `online_bad_debt`, `competitor_electronic_markdown`).

### §9.1 — First-time setup (lines 538–544): stale commands

- **Line 542:** `python -m zeal.cli init-db` — correct.
- **Line 543:** `python -m zeal.cli seed` — correct.
- **Line 544:** "Copy `scripts/launch_dashboard.ps1` to a desktop shortcut" — file does not exist.
- **Line 559:** `python -m zeal.cli migrate` — this command does not exist in `cli.py`.

### §14 — Acceptance criteria (lines 679–691): items not yet achievable

- **Criterion 4:** "The CardCash scraper produces observations for at least 50 merchants on a single refresh." — CardCash scraper not built; cannot be met.
- **Criterion 7:** "Test coverage on `pricing/` is 100%; on `ingestion/` is >=80%." — coverage not measured by tool in CI; may or may not be true.
- **Criterion 8:** "Test coverage on `ingestion/competitor/` is >=70%." — directory does not exist.
- **Criterion 10:** "The repo passes `ruff check` and `pytest` cleanly." — true. "Verified by an import-linter rule in CI." — no CI exists; no import-linter configured in `pyproject.toml`.

### §12 Q1 — eBay status date (line 638)

- "As of 2026-05-08, eBay has not yet responded" — current date is 2026-05-10; status is still blocked. Not wrong yet but will age.

---

## docs/decisions_log.md

### 2026-05-01 entry "eBay Browse API, not scraping eBay" (lines 65–69)

- **Line 65 heading:** "eBay Browse API, not scraping eBay" — This is the *original* (now superseded) decision. The 2026-05-05 entry explicitly corrects it ("eBay sold-listings access requires Marketplace Insights API, not Browse API"). The old entry is not deleted or struck through. A reader scanning headings could misread the old entry as current policy. The decisions_log is append-only by design, but the old heading is directly contradicted by a later entry. A reader note or cross-reference in the old entry would prevent confusion.

### 2026-05-01 entry "Scheduled refresh via Windows Task Scheduler" (lines 57–61)

- This decision was subsequently reversed (2026-05-04 entry: "Refresh model: on-demand only"). As with the Browse API entry, the reversal is documented as a new entry but the old heading "Scheduled refresh via Windows Task Scheduler" remains without a struck-through note. Not a code bug, but a reader scanning headings could pick up the wrong policy.

No code contradictions in decisions_log. Drift is heading-level only.

---

## docs/pricing_algorithm.md

**Assessment:** Solid and accurate. The eBay status statement at line 320 ("As of 2026-05-08") will age. No structural contradictions with code found.

- **Line 320:** "As of 2026-05-08, eBay has not yet responded" — still accurate as of 2026-05-10 audit; will need updating when eBay responds.
- **Line 499:** Lists "Operator action logging — reintroduce `published_prices` and `operator_actions`" in v2 roadmap — consistent with scope decisions.
- No references to Browse API as a valid fallback found in this doc.

---

## docs/spreadsheet_recon.md

Not read in full (large document). Spot-checked via grep for out-of-scope references.

```
grep -n "published_price\|operator_action\|Browse API\|scheduled refresh" docs/spreadsheet_recon.md
# Result: (no output)
```

No out-of-scope references found. Assessment: likely accurate (describes the spreadsheet artifact, not the live system).

---

## docs/credential_day_validation_plan.md

**Assessment:** Accurate and up to date. The 2026-05-07 and 2026-05-08 status sections correctly describe the production entitlement block.

- No Browse API fallback references as allowed paths.
- Out-of-scope items (§1) correctly list `ebay_weight` UI, schema changes, etc.
- "As of 2026-05-08, eBay has not yet responded" will need updating.
- **Line 12:** References `zeal_pricing_handoff_after_codex_prompt6.md` as a source. That file exists at the repo root but is otherwise unclassified (see audit 01).

---

## docs/dashboard_usability_review_plan.md

**Assessment:** Accurate to current state. Correctly describes what can and cannot be validated in synthetic mode.

- No out-of-scope feature references.
- "As of" eBay status implied but not date-stamped. Low staleness risk.

---

## docs/operator_demo_script.md

**Assessment:** Accurate. Correctly states the tool does not publish prices, blend CardCash, expose `ebay_weight`, or export CSVs. eBay status statements consistent with current blocked state.

- No out-of-scope features referenced as live.

---

## docs/historical_pricing_findings.md

Analyzed via spot grep. Content is historical analysis only, explicitly marked as not revising v1 algorithm or schema.

```
grep -n "published_price\|operator_action\|Browse API\|ebay_weight" docs/historical_pricing_findings.md
# Result: (no output)
```

No contradictions. Assessment: safe, reference-only.

---

## docs/historical_pricing_analysis.md

Not read in full; spot-checked.

```
grep -n "published_price\|operator_action\|Browse API\|scheduled refresh" docs/historical_pricing_analysis.md
# Result: (no output)
```

No contradictions found.

---

## Summary of highest-priority drift

| Priority | Document | Issue |
|---|---|---|
| High | `docs/architecture.md` §3 | 10+ phantom file paths in repo layout; `ingestion/competitor/` subtree does not exist |
| High | `docs/architecture.md` §5 step 4 | CardCash refresh described as implemented; it is not |
| Med | `docs/architecture.md` §9.1 | `scripts/launch_dashboard.ps1` and `zeal migrate` command do not exist |
| Med | `docs/architecture.md` §14 | Acceptance criteria 4, 8, 10 cannot be met (scraper not built; no CI) |
| Med | `docs/architecture.md` §8 | Engine pseudocode uses `@dataclass` but actual code uses Pydantic `BaseModel`; `GlobalConstants` fields incomplete |
| Low | `docs/decisions_log.md` | Old "Browse API" and "Scheduled refresh" headings not cross-referenced to superseding entries |
| Low | Multiple | "As of 2026-05-08" eBay status strings will become stale when eBay responds |
