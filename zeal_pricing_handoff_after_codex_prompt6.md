# Zeal Pricing Tool Handoff After Codex Prompt 6

## 1. Current Repository Status

- Repository: `rkplank/zeal-pricing-tool`
- Local branch: `main`
- Latest commit: `b485502bf0255cd6a114b4f29d70c974495cafca`
- Latest commit summary: `b485502 Commit all, Phase 3`
- Working tree status before this handoff file was created: clean
- Product status: v1 is feature-complete pending eBay Marketplace Insights approval and credentials.

## 2. What Landed

This PR completed the last pre-credential blocker for v1 live eBay readiness:

- Added Codex guidance files for repo-wide, pricing-package, and ingestion-package guardrails.
- Added environment-based configuration with synthetic/live eBay mode selection.
- Added `.env.example` for credential-day setup while keeping `.env` gitignored.
- Added a live/synthetic eBay client factory.
- Wired the FastAPI lifespan to create one shared `httpx.AsyncClient` and one configured eBay client.
- Preserved existing `app.state.ebay_client_factory` overrides for tests and custom clients.
- Added `zeal smoke-ebay --merchant <merchant_id> [--limit <int>]`.
- Added mocked tests for eBay OAuth and Marketplace Insights behavior.
- Added tests for config, client factory, smoke CLI, and app lifespan behavior.
- Updated README with live eBay readiness and credential-day procedure.

No real eBay credentials were added.

## 3. Files Changed

Latest commit `b485502` changed:

- `.env.example`
- `AGENTS.md`
- `README.md`
- `pyproject.toml`
- `uv.lock`
- `src/zeal/cli.py`
- `src/zeal/config.py`
- `src/zeal/ingestion/AGENTS.md`
- `src/zeal/ingestion/__init__.py`
- `src/zeal/ingestion/ebay_client_factory.py`
- `src/zeal/ingestion/ebay_errors.py`
- `src/zeal/ingestion/ebay_marketplace_insights_client.py`
- `src/zeal/ingestion/ebay_oauth.py`
- `src/zeal/pricing/AGENTS.md`
- `src/zeal/web/app.py`
- `tests/test_config.py`
- `tests/test_ebay_client_factory.py`
- `tests/test_ebay_marketplace_insights_client.py`
- `tests/test_ebay_oauth.py`
- `tests/test_smoke_ebay_cli.py`
- `tests/test_web_routes.py`

This handoff file is a follow-up documentation artifact.

## 4. Test Status

Final verification from a clean working tree after the commit:

```powershell
uv run ruff check .
```

Result: passed, `All checks passed!`

```powershell
uv run pytest
```

Result: passed, `460 passed`

```powershell
uv run mypy src
```

Result: passed, `Success: no issues found in 34 source files`

```powershell
git diff --check
```

Result: passed, no whitespace errors.

```powershell
rg "fastapi" src/zeal/ingestion/
```

Result: passed, no matches.

```powershell
rg "fastapi|sqlite3|httpx" src/zeal/pricing/
```

Result: passed, no matches.

```powershell
uv run python -m zeal.cli smoke-ebay --merchant home_depot
```

Result: passed in synthetic mode. Output included:

```text
Warning: ZEAL_EBAY_MODE=synthetic; using synthetic eBay client.
Merchant: Home Depot (home_depot)
Inclusion regex: home.*depot
Raw listings returned: 0
Valid listings: 0
Excluded listings: 0
```

```powershell
git status
```

Result before this handoff file: clean, branch up to date with `origin/main`.

## 5. Current v1 Product Definition

The Zeal Pricing Tool is a local-first, single-operator pricing decision-support dashboard for Zeal Cards.

It provides:

- A FastAPI read-only dashboard for reviewing merchant pricing recommendations.
- SQLite-backed local state.
- Spreadsheet-faithful pricing engine behavior validated against the legacy baseline.
- On-demand refresh workflow.
- Synthetic eBay mode by default.
- Live eBay Marketplace Insights client and OAuth flow ready to use once credentials are available.
- Credential-day smoke test command: `uv run python -m zeal.cli smoke-ebay --merchant home_depot`.
- Competitor/CardCash data as reference-only for v1.

It does not provide:

- Automated price publishing.
- Operator accept/override/skip workflow.
- Scheduled refresh.
- In-app config editing.
- Multi-user auth.
- CSV export.
- Website integration code.
- Competitor/CardCash influence on recommendations.

## 6. What Remains Before Live Use

Remaining external/live-use steps:

1. Receive eBay developer-program approval.
2. Confirm access is specifically Marketplace Insights, not Browse-only.
3. Copy `.env.example` to `.env`.
4. Fill `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET`.
5. Set `ZEAL_EBAY_MODE=live`.
6. Confirm `EBAY_ENVIRONMENT=production` unless intentionally testing sandbox.
7. Run the credential-day smoke test.
8. If the smoke test passes, restart the dashboard and run a manual refresh.
9. Spot-check 3-5 merchant detail pages.

## 7. Credential-Day Procedure

1. Wait for eBay developer-program approval; confirm access is Marketplace Insights, not Browse-only.
2. Copy `.env.example` to `.env`; fill `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`; set `ZEAL_EBAY_MODE=live`; confirm `EBAY_ENVIRONMENT`.
3. Run `uv run python -m zeal.cli smoke-ebay --merchant home_depot` or another known merchant.
4. Verify listing titles match the merchant, sale prices are non-zero, sold dates are recent, and post-filter valid count is non-zero.
5. If the smoke test passes, restart the dashboard, click "Refresh now," watch progress, and spot-check 3-5 merchant detail pages.
6. If the smoke test fails: `EbayAuthError` means credentials; `EbayRateLimitError` means pacing/quota; `EbayServerError`/`EbayNetworkError` means transient; otherwise inspect the stack trace.

## 8. Known Risks and Deferred Fixes

- Marketplace Insights access may be denied or may not be granted despite eBay developer-program approval.
- eBay search query is derived from `merchant.inclusion_regex`; some merchants may later need an explicit `merchant.ebay_search_query`.
- Face value extraction uses the largest dollar amount in the listing title; v2 may parse eBay item specifics if available.
- Competitor/CardCash remains reference-only/post-feedback and does not influence v1 recommendations.
- Live smoke testing has not happened yet because real credentials are still pending.
- Synthetic smoke output for `home_depot` currently returns zero listings because the synthetic client has no seeded live-listing payload; this is acceptable for mode/lifecycle verification, not a substitute for credential-day validation.

## 9. Guardrails for Future Work

- Treat `docs/pricing_algorithm.md` as the source of truth for pricing behavior.
- Keep `src/zeal/pricing/` pure: no web, database, network, environment, or filesystem dependencies.
- Keep `src/zeal/ingestion/` free of FastAPI/web imports.
- Do not put real eBay credentials in code, tests, fixtures, docs, or commit history.
- Do not hit live eBay APIs in automated tests; use mocks/respx or fakes.
- Preserve OAuth, retry, pagination, and face-value heuristic behavior unless a real smoke-test issue requires a scoped fix.
- Keep v1 scope narrow: no automated publishing, scheduled refresh, config UI, operator workflow, risk/watchlist UI, CSV export, or competitor influence without explicit scope change.
- Store and compute percentages as floats in `[0, 1]`.
- Keep `price_recommendations` append-only.
- Use `uv`; do not use `pip install` directly.

## 10. Suggested Opening Prompt For The Next Chat

```text
We are continuing in `rkplank/zeal-pricing-tool`.

Read `AGENTS.md`, `docs/pricing_algorithm.md`, `docs/architecture.md`, and `zeal_pricing_handoff_after_codex_prompt6.md`.

Current state:
- v1 is feature-complete pending eBay Marketplace Insights approval and credentials.
- Latest known commit is `b485502bf0255cd6a114b4f29d70c974495cafca`.
- Final clean-tree verification passed: ruff clean, mypy clean, `460 passed`, boundary rg checks clean, and synthetic `zeal smoke-ebay --merchant home_depot` succeeded.

Next task:
- If eBay credentials are available, perform credential-day validation using the README procedure.
- Do not commit credentials.
- If smoke test fails, diagnose only the live integration issue and keep fixes scoped.
- If credentials are still pending, do not add new v1 scope; prepare only documentation or operator-readiness polish explicitly requested.
```
