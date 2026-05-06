# AGENTS.md - src/zeal/pricing

Directory-specific guidance for Codex.

`src/zeal/pricing/` is the pure-function pricing engine boundary. This package must remain reusable by a future website integration without dragging in the local dashboard, SQLite, or network clients.

## Hard rules

- No database access.
- No network access.
- No FastAPI, Starlette, Jinja, HTMX, or template imports.
- No HTTP client libraries, request libraries, SQLite modules, environment-variable reads, file-system reads, or `datetime.now()`.
- No dependency on `src/zeal/web/`, `src/zeal/ingestion/`, or `src/zeal/db/`.
- Inputs should be explicit typed arguments; outputs should be typed return values.
- Keep behavior deterministic and unit-testable.

## Correctness source

Use `docs/pricing_algorithm.md` as the source of truth. Do not change pricing formulas, confidence rules, listing-filter behavior, sentinel handling, or golden-test tolerance unless the user explicitly approves a spec change.

## Testing expectations

Changes in this package should include or update branch-level unit tests and preserve golden baseline behavior.

Run at least:

```powershell
uv run pytest tests/test_pricing_engine_baseline.py tests/test_ebay_average.py tests/test_confidence.py tests/test_listing_filter.py tests/test_blending.py tests/test_competitor_aggregate.py -v
uv run mypy src
uv run ruff check .
Run the repository boundary search for forbidden web, database, and HTTP imports in this directory.
```

The `rg` boundary check should return nothing.
