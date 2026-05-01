# Zeal Pricing Tool

A decision-support tool that recommends gift card buy and sell prices for [Zeal Cards](https://zealcards.com/), replacing a manual spreadsheet workflow.

**Status:** Design phase — algorithm spec confirmed, architecture in progress. No code yet.

## What this is

Zeal Cards buys and sells gift cards across hundreds of merchants. Pricing has historically been done manually using a spreadsheet that pulls market data from eBay and applies per-merchant margin rules. This tool automates the data collection and computation, surfacing recommendations through a dashboard.

The operator retains full pricing authority. The tool is a guide, not an automated pricing system.

## What it does

- Pulls daily sold-listing data from eBay for every tracked merchant
- Applies the existing pricing logic (margins, channel costs, bad-debt rates) per merchant
- Produces buy and sell price recommendations across four channels: in-store, in-mail, electronic, online sell
- Flags low-confidence recommendations and large price movements for operator review
- Logs every operator override, building a dataset for future algorithm improvements

## What it isn't

- Not an automated pricing system (operator approves every change)
- Not integrated with the Zeal Cards website (separate tool; integration is a future possibility)
- Not multi-user (designed for one operator)

## Documentation

Design documents live in [`docs/`](./docs/):

- [`pricing_algorithm.md`](./docs/pricing_algorithm.md) — v1 algorithm specification (formulas, edge cases, v2 roadmap)
- [`architecture.md`](./docs/architecture.md) — system design (stack, schema, components, deployment)
- [`decisions_log.md`](./docs/decisions_log.md) — running record of design decisions and their rationale

## Stack (planned)

- Python 3.12+ with FastAPI
- SQLite for storage
- HTMX + Tailwind for the dashboard
- Runs locally on Windows; data refreshes scheduled via Task Scheduler

## Getting started

The tool isn't built yet. Once development begins, this section will cover installation, configuration, and daily use.

## Project layout

```
zeal-pricing-tool/
├── README.md
├── docs/                  Design documents
├── src/zeal/              Application code (forthcoming)
├── tests/                 Test suite (forthcoming)
├── scripts/               Setup and maintenance scripts (forthcoming)
└── data/                  SQLite database (gitignored)
```

## License

Proprietary. Internal tool for Zeal Cards.
