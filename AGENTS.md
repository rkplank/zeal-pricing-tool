# AGENTS.md

Guidance for Codex working in this repository.

## What this project is

The Zeal Pricing Tool is a local-first pricing decision-support dashboard for Zeal Cards. It recommends gift-card buy/sell prices while preserving final human pricing authority. It is not an automated price-publishing system.

The app is designed for a single operator on a Windows machine, backed by SQLite, served locally through FastAPI, and validated against the legacy spreadsheet baseline.

Authoritative design docs live in `docs/`:

- `docs/pricing_algorithm.md` - what the system computes: formulas, edge cases, confidence, scope.
- `docs/architecture.md` - how the system is built: stack, schema, data flow, deployment.
- `docs/decisions_log.md` - append-only design decisions and rationale.
- `docs/spreadsheet_recon.md` - findings from the source spreadsheet; inputs to the parser and baseline extraction.

Read the relevant docs before any non-trivial change. If code and docs disagree, treat the docs/spec as correct unless the user explicitly says the spec is being revised.

## Current v1 status

Current status as of 2026-06-14, foundation work complete (Python 3.12, entry point, truststore) — 2026-06-14:

- Phase 1 complete: spreadsheet parser, pricing engine, SQLite schema, golden baseline tests.
- FastAPI dashboard implemented with seeded/synthetic recommendations, merchant
  detail (pricing cards, price history chart, formula breakdown, eBay
  observations, competitor reference), and narrow merchant config editing.
- Listing filter, refresh orchestrator, refresh routes, dashboard refresh button,
  live/synthetic eBay client factory, `.env.example`, and `zeal smoke-ebay` CLI
  exist with mocked tests.
- **Production Marketplace Insights API access is NOT yet granted.** The sandbox
  keyset has the `buy.marketplace.insights` scope; the production keyset does
  not. Awaiting eBay support. v1 currently operates in synthetic mode.
- Narrow one-merchant-at-a-time merchant config editing is implemented for
  formula/config inputs with history logging.
- Competitor scraper Phase 1 foundation committed: `src/zeal/ingestion/competitor/`
  (`base.py`, `errors.py`, `__init__.py`). No CardCash scraper logic yet.
- Python standardized to 3.12.10 (python.org CPython); `python-preference =
  "only-system"` in `[tool.uv]`. Suite: **507 passing** on Python 3.12.
- `[project.scripts] zeal = "zeal.cli:main"` wired; `zeal seed/serve/smoke-ebay` resolve.
- `truststore` runtime dependency added; injected at CLI startup and app lifespan.
  Resolves `CERTIFICATE_VERIFY_FAILED` on Windows. Approved by operator 2026-06-14.

Update this section when the project state changes materially.

## Working principles

- **Spec authority.** `docs/pricing_algorithm.md` defines algorithm correctness. Do not change formulas, tolerances, sentinels, or edge cases without explicit instruction.
- **Small, reviewable changes.** One logical change per PR. Keep diffs limited to the requested scope.
- **No adjacent refactors.** Do not refactor nearby code "while here."
- **Flag ambiguity.** If the spec is silent, conflicting, or two interpretations are plausible, stop and surface the issue with the options.
- **No invented APIs.** If unsure about a library/API behavior, inspect existing code, tests, or official docs; otherwise write a small probe.
- **Tests are evidence.** A failing test usually means production code is wrong. Investigate before editing tests.

## Code organization

- `src/zeal/pricing/` is pure algorithm code: no I/O, no database, no network, no environment access, no `datetime.now()`, no FastAPI, no SQLite, no httpx.
- `src/zeal/ingestion/` owns external data clients and refresh orchestration. It may call pricing functions but must not import FastAPI.
- `src/zeal/db/` owns SQLite connection/schema/data-access helpers.
- `src/zeal/web/` owns FastAPI routes, templates, HTMX behavior, and app lifespan wiring.
- `src/zeal/models/` contains shared typed models.

Cross-layer imports flow inward: `web` and `ingestion` may import from `pricing`, `models`, and `db`. `pricing` must not import from `web`, `ingestion`, or `db`.

## Money and percentages

- Store and compute all percentages as floats in `[0, 1]`: use `0.875`, never `87.5` or `"87.5%"`.
- Currency is USD only.
- Percent-string formatting belongs only in UI/display code.
- Golden baseline tolerance is `+/-0.001`; do not tighten or loosen it without explicit approval.

## Database rules

- SQLite file path defaults to `data/zeal.db`.
- Canonical schema lives in `src/zeal/db/schema.sql` only. `apply_schema()` in `src/zeal/db/connection.py` runs it via `conn.executescript()` — idempotent on new databases (`CREATE TABLE IF NOT EXISTS`), but does **not** `ALTER TABLE` existing ones. There is no `src/zeal/db/migrations/` directory.
- When schema changes land, apply new columns via `ALTER TABLE` on the existing DB, or delete and re-seed. Confirm no unreproducible production data exists before re-seeding.
- Timestamps are ISO 8601 UTC text.
- Merchants are deactivated with `is_active = 0`; do not delete merchants.
- `price_recommendations` is append-only and is the system of record for recommendations.
- `competitor_observations` is append-only and is the system of record for competitor pricing history. Never delete or update rows; re-runs append new observations.
- Do not reintroduce `published_prices`, `operator_actions`, risk/watchlist columns, or user/auth tables in v1.

## v1 scope guardrails

Do not add any of the following unless the user explicitly changes scope:

- Automated price publishing.
- Operator accept/override/skip workflow.
- Scheduled refresh.
- CSV export.
- Global constants editor.
- Bulk merchant config editing.
- Multi-user auth.
- `ebay_weight` UI.
- Competitor/CardCash influence on v1 recommendations.
- Risk/watchlist fields or UI.
- Website integration code.
- Recency weighting, outlier filtering, partial-balance parsing, dynamic tier reassignment, bankruptcy detection, or internal sale-history inputs.

Competitor data is reference-only in v1.

A narrow merchant config editor is now in v1 scope only for formula/config
inputs such as margins, eligibility, regexes, and config override fields, with
history logging. It is not operator action tracking and must not reintroduce
published price workflow, accept/override/skip state, or `operator_actions`.

## eBay/live-data rules

- Sold-listing data requires the eBay Marketplace Insights API, not Browse API.
- Do not validate against the real eBay API in tests.
- Do not put real eBay credentials in code, tests, fixtures, docs, or commit history.
- All eBay HTTP tests must use mocks/respx fixtures.
- The credential-day smoke test is an operator CLI command, not a unit test against the live API.
- Preserve the existing live client retry behavior, OAuth token flow, and face-value heuristic unless a real smoke-test issue justifies a change.

## Tooling commands

Use `uv`; do not run `pip install` directly.

```powershell
uv sync
uv run ruff check .
uv run pytest
uv run mypy src
git diff --check
```

For targeted checks after the mode-toggle/smoke-test PR:

```powershell
uv run pytest tests/test_config.py tests/test_ebay_client_factory.py tests/test_smoke_ebay_cli.py -v
uv run ruff check .
uv run mypy src
rg "fastapi" src/zeal/ingestion/
rg "fastapi|sqlite3|httpx" src/zeal/pricing/
```

Expected boundary checks:

- `rg "fastapi" src/zeal/ingestion/` returns nothing.
- `rg "fastapi|sqlite3|httpx" src/zeal/pricing/` returns nothing.

## PR expectations

Before presenting work as complete:

1. Summarize files changed and why.
2. List tests/commands run and their results.
3. Note any skipped verification honestly.
4. Confirm the diff stayed within the requested scope.
5. Mention any follow-up that is truly external, such as eBay credential approval.

## When uncertain

Stop and ask only when continuing would risk a wrong architectural or pricing decision. Otherwise, make the smallest safe change consistent with the specs and tests, and document assumptions in the PR summary.
