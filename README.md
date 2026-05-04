# Zeal Pricing Tool

Zeal Pricing Tool is a local-first pricing decision-support tool for Zeal Cards.
It helps a single operator review gift card buy and sell recommendations while
preserving final human pricing authority. It is not automated price publishing.

## Current Status

Phase 1 foundation is implemented:

- Spreadsheet parser for the legacy workbook baseline
- Pricing engine that validates spreadsheet-faithful behavior
- SQLite schema scaffold
- Golden baseline fixture covering the extracted spreadsheet records
- Tests for parser behavior, merchant models, eBay averaging, confidence, schema,
  and pricing formulas

The current codebase proves that the March 2022 spreadsheet logic can be ported
faithfully. At default `ebay_weight = 1.0` with no competitor aggregate, the
engine is expected to match the spreadsheet baseline within the golden-test
tolerance.

The revised v1 documents in `docs/` define the intended product direction:
operator-facing recommendations with formula breakdowns, risk flags, eBay
listing validity tracking, and future competitor blending. This repository is
currently synchronized to that v1 scaffold, but live ingestion and the full
dashboard are not complete.

Phase 2 is pending client/operator clarification and confirmation of eBay
sold-listings access. Do not assume live eBay collection, CardCash scraping,
production refresh jobs, deployment scripts, or automated publishing are present.

## Scope

This tool is designed to be:

- Local-first
- Single-operator
- Windows-targeted
- SQLite-backed
- A recommendation and review workflow, not an automated pricing system

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
|   |-- jobs/              placeholder package for future refresh jobs
|   `-- web/               placeholder package for future dashboard work
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
