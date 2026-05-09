# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

The Zeal Pricing Tool: a decision-support dashboard that recommends gift card buy/sell prices for Zeal Cards, replacing a manual spreadsheet. Single operator, single Windows machine, local deployment.

Authoritative design docs live in `docs/`:

- `pricing_algorithm.md` — what the system computes (formulas, edge cases, scope)
- `architecture.md` — how it's built (stack, schema, layout, deployment)
- `decisions_log.md` — design decisions and rationale
- `spreadsheet_recon.md` — findings from analysis of the source spreadsheet; inputs to the parser

Read the relevant section before making any non-trivial change. The spec is the source of truth: if code disagrees with the spec, the code is wrong unless explicitly told otherwise.

## Current phase and status

Current status as of 2026-05-09, latest verified commit
`c9fe166c0ffb42db08a56208d5b3bf5b9e4ae602`:

- Phase 1 is complete: spreadsheet parser, pure pricing engine, SQLite schema,
  seeded baseline data, and golden tests validate spreadsheet-faithful behavior
  within +/-0.001.
- The FastAPI read-only dashboard is implemented with seeded/synthetic
  recommendations, pricing list, merchant detail pages, formula breakdowns,
  refresh controls, and status display.
- The live eBay Marketplace Insights path exists behind configuration:
  live/synthetic client factory, OAuth flow, Marketplace Insights client,
  `zeal smoke-ebay`, refresh orchestrator, and mocked tests.
- Production validation is blocked. The production eBay keyset cannot mint
  `buy.marketplace.insights`; eBay has not yet responded with production
  Marketplace Insights entitlement.
- Synthetic dashboard polish and documentation alignment are complete while
  waiting for eBay.
- Narrow one-merchant-at-a-time merchant config editing is now approved for v1
  scope, but not implemented yet.

Do not run live eBay validation until production `buy.marketplace.insights` is
enabled. Do not fall back to Browse API; Browse does not provide sold-listing
data and is not an acceptable substitute for Marketplace Insights.

## Working principles

- **Spec authority.** `docs/pricing_algorithm.md` defines correctness. Don't deviate without an explicit instruction.
- **Stay in scope.** Don't add features from the v2 roadmap (`pricing_algorithm.md` §10). Don't pre-build later-phase components.
- **Stay in your lane.** Don't touch files outside the explicit scope of the current task. Don't refactor adjacent code "while you're here."
- **Flag rather than guess.** If a spec is silent or genuinely ambiguous, surface the question. Don't pick a plausible interpretation silently. Open questions in `pricing_algorithm.md` §11 should be flagged if hit, not resolved.
- **No invented APIs.** If unsure whether a library function exists or behaves as you expect, check the docs or write a tiny probe. Don't assume.
- **Small, reviewable changes.** One logical change per commit. Commit messages name what changed, not how.

## Conventions

### Money and percentages

- All percentages are stored and computed as floats in `[0, 1]`. `0.875`, never `87.5` or `"87.5%"`.
- Currency is USD only. No multi-currency handling.
- Formatting to percent strings happens only at the UI/display layer (not in Phase 1).

### Code organization

- `src/zeal/pricing/` is **pure**: no I/O, no database, no network, no `datetime.now()`, no environment access. Pure functions over typed inputs. This is the most heavily tested module in the repo.
- `src/zeal/ingestion/` owns all eBay interaction (Phase 2).
- `src/zeal/db/` owns all database I/O.
- `src/zeal/web/` owns all HTTP/UI (Phase 3).
- `src/zeal/models/` is shared types only; depends on nothing else in `src/zeal/`.

Cross-layer imports flow inward: `web` and `ingestion` may import from `pricing`, `models`, and `db`. `pricing` imports only from `models`. `models` imports nothing from `src/zeal/`.

### Types

- Pydantic v2 for data crossing module boundaries (config records, API payloads, DB rows).
- `@dataclass(frozen=True)` for internal pricing-engine inputs/outputs.
- Type-annotate everything. `mypy src/zeal` is expected to pass.

### Tests

- Pure functions in `pricing/` have unit tests per branch *and* golden tests against the spreadsheet baseline.
- Golden test tolerance is `±0.001`. Don't tighten or loosen.
- Test files mirror source layout (`tests/test_pricing_engine.py` ↔ `src/zeal/pricing/engine.py`).
- Use `pytest` and `pytest-asyncio`. No other frameworks.
- A failing test means the production code is wrong, not that the test is wrong. Investigate before "fixing."

### Tooling

- Python 3.12+. Dependencies managed by `uv`. Never invoke `pip install` directly; edit `pyproject.toml` and run `uv sync`.
- `ruff check` and `ruff format` must pass before commit.
- Do not add new runtime dependencies without explicit approval. Adding to `[dependency-groups]` (dev tools) is fine to ask about; adding to runtime `dependencies` requires a yes.

### Database

- SQLite at `data/zeal.db` (gitignored).
- Canonical schema is `src/zeal/db/schema.sql` plus numbered migrations in `src/zeal/db/migrations/`.
- All percentages stored as `REAL` in `[0, 1]`. All timestamps as ISO 8601 UTC text.
- Merchants are deactivated (`is_active = 0`), never deleted. Same for global constants — history matters.

## What not to do in v1 without explicit scope change

- Do not change pricing formulas, sentinels, confidence rules, or golden
  tolerance.
- Do not change the SQLite schema or add migrations unless the task explicitly
  requires it.
- Do not run live eBay validation while production Marketplace Insights
  entitlement is blocked.
- Do not use Browse API fallback for sold listings.
- Do not put real eBay credentials in code, tests, fixtures, docs, or commit
  history.
- Do not add automated publishing, accept/override/skip workflow, scheduled
  refresh, CSV export, global constants editing, bulk merchant config editing,
  multi-user auth, `ebay_weight` UI, CardCash blending, risk/watchlist fields,
  website integration, or internal sale-history inputs.
- A narrow merchant config editor is now in v1 scope only for formula/config
  inputs such as margins, eligibility, regexes, and config override fields, with
  history logging. It is not operator action tracking and must not reintroduce
  published price workflow, accept/override/skip state, or `operator_actions`.
- Do not add a logging/telemetry framework. Standard library `logging` is enough
  until proven otherwise.

## When you hit something unclear

Stop and ask. Specifically:

- Spec genuinely silent on a case → ask.
- Two reasonable interpretations of a spec sentence → ask, propose the candidates.
- A library doesn't behave the way you expected → say so before working around it.
- A test fails in a way you don't understand → don't modify the test; investigate the production code.
- The spreadsheet shows a value that disagrees with what the engine computes → flag, don't paper over.

The cost of pausing is small. The cost of plausible-but-wrong silent decisions in this codebase is large because the golden test suite can mask them: if the baseline is wrong and the engine is wrong in matching ways, everything passes and the bug ships.
