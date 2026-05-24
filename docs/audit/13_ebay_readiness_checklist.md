# Audit Report 13 — eBay Credential-Day Readiness Checklist

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review  
**Verified against:** current code on this branch after Phase 1–3 changes

Binary pass/fail for each item. Every item must be PASS before credential day.

---

## A. Config-only credential-day flip

| # | Check | Result | Evidence |
|---|---|---|---|
| A1 | Flipping from synthetic to live mode requires only `.env` changes; no code edits | **PASS** | `ZEAL_EBAY_MODE` controls the factory gate; `create_ebay_client()` reads only from `ZealConfig` |
| A2 | Sandbox vs. production is controlled by `EBAY_ENVIRONMENT` env var; no code edits required | **PASS** | `_read_ebay_environment()` reads env; `_BASE_URLS[environment]` selects endpoint at construction |
| A3 | The default for `ZEAL_EBAY_MODE` is `"synthetic"` (safe default) | **PASS** | `config.py:63`: `os.environ.get("ZEAL_EBAY_MODE", "synthetic")` |
| A4 | The default for `EBAY_ENVIRONMENT` is `"production"` (correct credential-day default) | **PASS** | `config.py:70`: `os.environ.get("EBAY_ENVIRONMENT", "production")` |
| A5 | Config reads on restart; no process-level caching that would survive a restart | **PASS** | `app.py:33`: `config = ZealConfig.from_env()` called every lifespan startup |

---

## B. OAuth scope handling

| # | Check | Result | Evidence |
|---|---|---|---|
| B1 | OAuth scope is centralized to a single constant | **PASS** | `ebay_oauth.py:11`: `_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"` |
| B2 | The scope constant is used without duplication in the OAuth request body | **PASS** | `ebay_oauth.py:69`: `f"&scope={_SCOPE}"` |
| B3 | The scope constant is used without duplication in the error message | **PASS** | `ebay_oauth.py:98`: `f"Insights scope {_SCOPE}."` (fixed Phase 3) |
| B4 | An `invalid_scope` error raises `EbayAuthError` with a clear diagnostic message | **PASS** | `ebay_oauth.py:87–88`: `if error == "invalid_scope": raise EbayAuthError(_invalid_scope_message(...))` |
| B5 | The diagnostic message names the environment, the scope, and the Developer Portal path | **PASS** | `_invalid_scope_message()` output: "The production keyset cannot mint ... Check the eBay Developer Portal under Production -> Client Credential Grant Type scopes" |
| B6 | OAuth scope is not configurable via env (intentional: we always need MI; wrong scope = clear error) | **PASS** | `_SCOPE` is a module constant, not read from env; changing it requires a code change, which is correct |

---

## C. Browse API fallback

| # | Check | Result | Evidence |
|---|---|---|---|
| C1 | No Browse API URL appears in source code | **PASS** | `grep -rn "buy/browse\|browse/v1" src/zeal/ --include="*.py"` → no output |
| C2 | No `findCompletedItems` or Browse-equivalent call exists | **PASS** | Same grep; no matches |
| C3 | `ebay_client_factory.py` returns only `SyntheticEbayClient` or `EbayMarketplaceInsightsClient` | **PASS** | `ebay_client_factory.py`: two branches, no third branch |
| C4 | An `invalid_scope` error does NOT trigger a fallback; it raises and propagates | **PASS** | Error propagates from `_fetch()` → `sold_listings_for_merchant()` → `_process_ebay()` → per-merchant `except Exception` handler → logs and marks merchant as errored |

---

## D. Synthetic mode isolation

| # | Check | Result | Evidence |
|---|---|---|---|
| D1 | `SyntheticEbayClient` has no HTTP client, no URL, no network code | **PASS** | `ebay_client.py:22–39`: in-memory dict; no `httpx` import |
| D2 | Refresh route returns 409 when `ebay_mode == "synthetic"` | **PASS** | `web/routes/refresh.py:95–100`: `if ... "synthetic": return HTMLResponse(status_code=409, ...)` |
| D3 | The refresh background task's factory correctly returns the live client when mode is `live` | **PASS** | `app.py:36–38`: lifespan constructs `EbayMarketplaceInsightsClient` when `config.ebay_mode == "live"` and wires it as the factory |
| D4 | Synthetic mode cannot be entered accidentally during a live-mode run | **PASS** | Mode is set at startup from env and cached in `app.state.zeal_config`; only a restart + env change can flip modes |

---

## E. Error handling — no silent fallbacks

| # | Check | Result | Evidence |
|---|---|---|---|
| E1 | A per-merchant `EbayAuthError` is logged and the merchant is marked errored | **PASS** | `refresh.py:79–83`: `except Exception: logger.exception(...)` + `errored.append(merchant_id)` |
| E2 | A full-run exception marks the refresh_run row as `failed` in the DB | **PASS** | `refresh.py:118–131`: outer `except Exception` writes `status = 'failed'` and re-raises |
| E3 | The background task wrapper logs uncaught exceptions | **PASS** | `web/routes/refresh.py:83–84`: `except Exception: logger.exception("Uncaught exception in background refresh task")` |
| E4 | A failed refresh does NOT silently use synthetic recommendations | **PASS** | `run_refresh()` writes new rows only when data is obtained; a failed merchant keeps its prior `price_recommendations` row; no row is written substituting synthetic data |
| E5 | The refresh status surface to the operator shows `partial` or `failed` — not `completed` — when merchants error | **PASS** | `refresh.py:94–96`: `status = "completed" if not errored else "partial"` |

---

## F. Secrets and credentials

| # | Check | Result | Evidence |
|---|---|---|---|
| F1 | `.env` is gitignored | **PASS** | `.gitignore:7`: `.env` |
| F2 | `.env` is not staged | **PASS** | `git status --short .env` → no output |
| F3 | No real credentials are hardcoded in source or tests | **PASS** | Audit 06: grep for credential values returned no matches |
| F4 | OAuth credentials are never logged | **PASS** | Audit 06: no `logger.*` call references `client_id`, `client_secret`, or `_credentials` |
| F5 | The OAuth token itself is never logged | **PASS** | Token is stored as `self._token` and passed in headers; no log statement references it |

---

## G. Test suite

| # | Check | Result | Evidence |
|---|---|---|---|
| G1 | `uv run pytest` passes with 493 tests | **PASS** | Confirmed after every Phase 1–3 change |
| G2 | `uv run ruff check .` passes | **PASS** | Confirmed |
| G3 | `uv run mypy src` passes | **PASS** | 34 source files, no issues |
| G4 | OAuth token flow tests cover 401, 429, invalid_scope, and success paths | **PASS** | `test_ebay_oauth.py`: multiple test functions covering these paths |
| G5 | Live client retry tests cover 401 token refresh, 429 back-off, 5xx retry, network error | **PASS** | `test_ebay_marketplace_insights_client.py` |
| G6 | Factory correctly creates synthetic vs. live client based on config | **PASS** | `test_ebay_client_factory.py` |

---

## H. Runbook readiness

| # | Check | Result | Evidence |
|---|---|---|---|
| H1 | Credential day runbook exists with exact copy-paste commands | **PASS** | `docs/credential_day_runbook.md` created in Phase 4 |
| H2 | Runbook includes kill criteria and rollback procedure | **PASS** | §8 Rollback and per-stage kill criteria tables |
| H3 | Runbook instructs operator not to start dashboard before smoke test | **PASS** | §2 explicitly says "Do not start the dashboard yet" |
| H4 | Runbook covers what to share with eBay support if scope is not granted | **PASS** | §9 |
| H5 | Runbook does not contain real credentials or instruct operator to commit `.env` | **PASS** | All credential fields shown as `<variable_name>` placeholders |

---

## Overall readiness: PASS

All 35 checklist items pass. The codebase is ready for credential day. The only
remaining external dependency is eBay granting `buy.marketplace.insights` on the
production keyset.

**Open items not blocking credential day:**
- `per_call_sleep_ms` is hardcoded at 100ms (see `11_followups.md` #10); adjust
  post-credential-day based on observed quota behavior.
- Test gaps from `10_bugs_to_review.md` BUG-05 and BUG-06; add before the
  first full-fleet live refresh.
