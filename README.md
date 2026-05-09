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

The dashboard now supports review, synthetic-mode usability review, and the live
eBay smoke/refresh path. A narrow merchant config editor is approved for v1
scope but has not been built yet. Production validation is currently blocked
because the production eBay keyset cannot mint the `buy.marketplace.insights`
scope. eBay has not yet responded with production Marketplace Insights
entitlement.

Synthetic mode is the correct current workstream: use it to review table
scannability, labels, merchant detail pages, formula explanations, and operator
workflow before live sold-listing access is available. Synthetic baseline rows
come from the validated spreadsheet fixture; they are not current live market
prices.

CardCash competitor data remains reference-only/post-feedback. Do not assume
automated publishing, scheduled refresh, operator workflow, or deployment
scripts are present.

## Credential-Day Procedure

1. Wait for eBay to enable production Marketplace Insights entitlement. Confirm `buy.marketplace.insights` is available for the production Client Credential Grant Type scopes; Browse API fallback is not allowed.
2. Copy `.env.example` to `.env`; fill `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`; set `ZEAL_EBAY_MODE=live`; confirm `EBAY_ENVIRONMENT`.
3. Run `uv run python -m zeal.cli smoke-ebay --merchant home_depot` or another known merchant.
4. Verify listing titles match the merchant, sale prices are non-zero, sold dates are recent, and post-filter valid count is non-zero.
5. If the smoke test passes, restart the dashboard, click "Refresh now," watch progress, and spot-check 3-5 merchant detail pages.
6. If the smoke test fails: `EbayAuthError` means credentials; `EbayRateLimitError` means pacing/quota; `EbayServerError`/`EbayNetworkError` means transient; otherwise inspect the stack trace.

## Scope

This tool is designed to be:

- Local-first, single-operator, Windows-targeted
- A review dashboard the operator runs on demand, with a narrow merchant config
  editor in v1 scope
- An append-only historical record of every pricing recommendation produced
- Spreadsheet-faithful in v1 (algorithm matches the legacy spreadsheet)
- Forward-compatible with future website integration (the engine is a pure-function library importable by other consumers)

Not in scope:

- Automated price publishing of any kind
- Operator action tracking
- Scheduled refresh
- Global constants editing
- Bulk merchant config editing
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
|   |-- ingestion/         eBay clients and refresh orchestration
|   |-- jobs/              placeholder; v1 has no scheduled jobs
|   `-- web/               FastAPI dashboard list/detail and on-demand refresh routes
|-- tests/                 unit tests and golden baseline test
`-- data/                  local runtime data location
```

## Development

Install dependencies with the project environment manager, then run:

```powershell
uv run ruff check .
uv run pytest
uv run mypy src
```

The golden baseline fixture is stored at
`tests/fixtures/spreadsheet_baseline.json`. Parser behavior should remain
faithful to the spreadsheet reconciliation notes; do not weaken row
classification or merchant slug tests to make unrelated changes pass.

## License

Proprietary. Internal tool for Zeal Cards.
