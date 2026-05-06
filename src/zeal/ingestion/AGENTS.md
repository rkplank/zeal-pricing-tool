# AGENTS.md - src/zeal/ingestion

Directory-specific guidance for Codex.

`src/zeal/ingestion/` owns external data collection seams, eBay client code, OAuth, client factories, and refresh orchestration. It may call pure pricing functions, but it must not become a web/UI layer.

## Hard rules

- Do not import FastAPI, Starlette, Jinja, or dashboard templates here.
- Do not put real eBay credentials in code, tests, fixtures, or documentation.
- Do not hit the live eBay API in automated tests.
- Use mocks/respx fixtures for eBay HTTP behavior.
- Preserve existing retry, OAuth, pagination, and face-value extraction behavior unless a real issue requires a scoped change.
- Keep the app integration seam narrow: the web layer should obtain a configured `EbayClient`; ingestion should not know about routes/templates.

## Current live eBay assumptions

- Sold listings require eBay Marketplace Insights API.
- Browse API is not a valid source for sold listings.
- Live credential validation happens through the operator-facing `zeal smoke-ebay` command after eBay approval.

## Testing expectations

Run targeted ingestion tests plus full verification when touching live client, OAuth, factory, or refresh code:

```powershell
uv run pytest tests/test_ebay_oauth.py tests/test_ebay_marketplace_insights_client.py tests/test_ebay_client_factory.py tests/test_refresh_orchestrator.py -v
uv run mypy src
uv run ruff check .
Run the repository boundary search for forbidden web-framework imports in this directory.
```

The boundary check should return nothing.
