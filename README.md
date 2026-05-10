# Zeal Pricing Tool

Zeal Pricing Tool is a local-first, single-operator, Windows-targeted pricing
decision-support dashboard for Zeal Cards. It recommends gift-card buy and sell
prices while preserving final human pricing authority. It is **not** an automated
price-publishing system. The dashboard shows saved tool recommendations only; it
does not display, record, or affect prices Zeal actually publishes.

## Current Status

Phase 1 foundation is complete:

- Spreadsheet parser for the legacy workbook baseline
- Pricing engine that validates spreadsheet-faithful behavior at default `ebay_weight = 1.0`
- SQLite schema and seeded baseline data
- Golden baseline fixture covering 281 spreadsheet records
- FastAPI dashboard with pricing list, merchant detail, formula breakdown, price
  history chart, and narrow merchant config editor
- Tests for parser behavior, merchant models, eBay averaging, confidence, schema,
  blending, competitor aggregation, and pricing formulas

**Current operating mode: Synthetic baseline.** Production Marketplace Insights
API access is NOT yet granted. The sandbox keyset has the
`buy.marketplace.insights` scope; the production keyset does not. Zeal is
awaiting eBay support. Until access is granted, the dashboard runs in synthetic
mode using seeded spreadsheet-baseline recommendations. Synthetic rows are useful
for reviewing layout, labels, formula explanations, and operator workflow. They
are not current live market prices.

CardCash competitor data remains reference-only and not yet automated.
Do not assume automated publishing, scheduled refresh, operator workflow, or
deployment scripts are present.

## Credential-Day Procedure

When eBay enables production `buy.marketplace.insights` access:

1. Confirm `buy.marketplace.insights` appears under the production Client Credential
   Grant Type scopes in the eBay Developer Portal. Browse API alone is not
   sufficient; it provides active listings only, not sold listings.
2. Copy `.env.example` to `.env`; fill `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`;
   set `ZEAL_EBAY_MODE=live`; confirm `EBAY_ENVIRONMENT=production`.
3. Run `uv run python -m zeal.cli smoke-ebay --merchant home_depot --limit 10`.
4. Verify listing titles match the merchant, sale prices are non-zero, sold dates
   are recent, and post-filter valid count is non-zero.
5. If the smoke test passes, restart the dashboard, click "Refresh now", watch
   progress, and spot-check 3-5 merchant detail pages.
6. If the smoke test fails: `EbayAuthError` means credentials or scope;
   `EbayRateLimitError` means pacing/quota; `EbayServerError`/`EbayNetworkError`
   means transient; otherwise inspect the stack trace.

## Scope

This tool is designed to be:

- Local-first, single-operator, Windows-targeted
- A review dashboard the operator runs on demand, with a narrow merchant config
  editor for formula/config inputs
- An append-only historical record of every pricing recommendation the tool has
  produced
- Spreadsheet-faithful in v1 (algorithm matches the legacy spreadsheet)

Not in scope:

- Automated price publishing of any kind
- Operator action tracking
- Scheduled refresh
- Global constants editing
- Bulk merchant config editing
- Multi-user / authentication
- CSV export
- `ebay_weight` UI (field exists in schema and engine, locked at 1.0)
- CardCash or other competitor blending into recommendations

## What the Dashboard Shows

- **Pricing list:** all active merchants, latest saved recommendations, delta
  columns, confidence badges, source labels (Synthetic baseline / Live eBay /
  Config override / No Data)
- **Merchant detail:** latest recommendation cards, "Why this recommendation?"
  summary, price history chart (saved tool recommendations only — not prices
  published or applied outside the tool), formula breakdown, recent and excluded
  eBay observations, competitor reference panel (reference-only), recommendation
  history table, recent refresh status
- **Config editor:** one-merchant-at-a-time editing of formula inputs (margins,
  eligibility, regexes, override fields) with history logging

The dashboard does not display or record prices Zeal has published, prices
customers have received, or any operator action taken outside the tool.

## Documentation

Source-of-truth planning documents live in `docs/`:

- `docs/pricing_algorithm.md` — v1 algorithm specification
- `docs/architecture.md` — local architecture and data model
- `docs/decisions_log.md` — design decisions and rationale
- `docs/spreadsheet_recon.md` — spreadsheet reconciliation findings

## Project Structure

```text
zeal-pricing-tool/
|-- docs/                  v1 specs, architecture, decisions, recon notes
|-- scripts/               spreadsheet extraction and baseline tooling
|-- src/zeal/
|   |-- db/                SQLite connection, schema, repositories, seeder
|   |-- models/            Pydantic data models
|   |-- pricing/           pure pricing, blending, filters, aggregation helpers
|   |-- ingestion/         eBay clients and refresh orchestration
|   |-- jobs/              placeholder; v1 has no scheduled jobs
|   `-- web/               FastAPI dashboard routes, templates, static assets
|-- tests/                 unit tests and golden baseline tests
`-- data/                  local runtime data location (gitignored)
```

## Development

Install dependencies, then run:

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
