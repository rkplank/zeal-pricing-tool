# Zeal Pricing Tool

Zeal Pricing Tool is a local-first pricing decision-support tool for Zeal Cards.
It helps a single operator review gift card buy and sell recommendations while
preserving final human pricing authority. It is not automated price publishing.

## Current Status

Phase 1 foundation is complete:

- Spreadsheet parser for the legacy workbook baseline
- Pricing engine that validates spreadsheet-faithful behavior at default `ebay_weight = 1.0`
- SQLite schema scaffold
- Golden baseline fixture covering 281 spreadsheet records
- Tests for parser behavior, merchant models, eBay averaging, confidence, schema,
  blending, competitor aggregation, and pricing formulas

The current codebase proves that the March 2022 spreadsheet logic ports
faithfully. The engine matches the spreadsheet baseline within +/-0.001 across
all 281 baseline merchants.

Phase 2 begins after eBay Browse API access is approved. The four phases ahead
-- read-only viewer with synthetic data (Phase 2), on-demand eBay refresh
(Phase 3), CardCash competitor scraper (Phase 4), polish and stabilize
(Phase 5) -- are scoped in `docs/architecture.md` §11.

Do not assume live eBay collection, CardCash scraping, refresh job, deployment
scripts, or dashboard UI are present yet.

## Scope

This tool is designed to be:

- Local-first, single-operator, Windows-targeted
- A read-only review dashboard the operator runs on demand
- An append-only historical record of every pricing recommendation produced
- Spreadsheet-faithful in v1 (algorithm matches the legacy spreadsheet)
- Forward-compatible with future website integration (the engine is a pure-function library importable by other consumers)

Not in scope:

- Automated price publishing of any kind
- Operator action tracking
- Scheduled refresh
- In-app config editing
- Multi-user / authentication
- CSV export

## Documentation

Source-of-truth planning documents live in `docs/`:

- `docs/pricing_algorithm.md` - v1 algorithm specification
- `docs/architecture.md` - local architecture and data model direction
- `docs/decisions_log.md` - design decisions and open questions
- `docs/spreadsheet_recon.md` - spreadsheet reconciliation findings

## Project Structure

```text
zeal-pricing-tool/
|-- docs/                  v1 specs, architecture, decisions, recon notes
|-- scripts/               spreadsheet extraction and baseline tooling
|-- src/zeal/
|   |-- db/                SQLite connection and schema
|   |-- models/            Pydantic data models
|   |-- pricing/           pure pricing, blending, filters, aggregation helpers
|   |-- ingestion/         placeholder package for future ingestion work
|   |-- jobs/              placeholder; v1 has no scheduled jobs
|   `-- web/               FastAPI dashboard list/detail and on-demand refresh routes; partial in Phase 2
|-- tests/                 unit tests and golden baseline test
`-- data/                  local runtime data location
```

## Development

Install dependencies with the project environment manager, then run:

```powershell
ruff check .
pytest
mypy src
```

The golden baseline fixture is stored at
`tests/fixtures/spreadsheet_baseline.json`. Parser behavior should remain
faithful to the spreadsheet reconciliation notes; do not weaken row
classification or merchant slug tests to make unrelated changes pass.

## License

Proprietary. Internal tool for Zeal Cards.
