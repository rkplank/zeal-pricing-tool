# Audit Report 05 — eBay Integration Review

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review  
**Phase 4 re-verification:** 2026-05-10 — all findings below re-checked against
current code after Phase 3 changes. Two items from §4 and §6 are now resolved;
see notes inline.

---

## 1. Every eBay touch point in `src/zeal/`

### `src/zeal/config.py` — environment reads

| Line | Symbol | What it does | Sandbox vs. production | MI vs. Browse |
|---|---|---|---|---|
| 26 | `load_dotenv()` | Reads `.env` into `os.environ` before any read | N/A | N/A |
| 30 | `_optional_env("EBAY_CLIENT_ID")` | Reads client ID | Not distinguished here; `EbayEnvironment` carries the distinction | N/A |
| 31 | `_optional_env("EBAY_CLIENT_SECRET")` | Reads client secret | Same | N/A |
| 32 | `os.environ.get("ZEAL_DB_PATH", ...)` | DB path; not eBay | N/A | N/A |
| 63 | `_read_ebay_mode()` → `ZEAL_EBAY_MODE` | Returns `"synthetic"` or `"live"` | Separate from environment; controls client class | Controls whether any eBay call is made |
| 70 | `_read_ebay_environment()` → `EBAY_ENVIRONMENT` | Returns `"production"` or `"sandbox"` | **Explicit distinction; validated** | N/A |

**Assessment:** config layer correctly separates mode (synthetic/live) from environment (sandbox/production). Default for `ZEAL_EBAY_MODE` is `"synthetic"` — safe default; no accidental live calls. Default for `EBAY_ENVIRONMENT` is `"production"` — correct credential-day default. Both are validated with `ValueError` on bad values.

---

### `src/zeal/ingestion/ebay_oauth.py` — OAuth token minting

| Line | Symbol | What it does |
|---|---|---|
| 11 | `_SCOPE` | `"https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"` — **hardcoded; single definition** |
| 15–18 | `_BASE_URLS` | Maps `"production"` → `https://api.ebay.com`; `"sandbox"` → `https://api.sandbox.ebay.com` |
| 40 | `self._token_url` | Set from `_BASE_URLS[environment]` in `__init__` — **sandbox vs. production correctly routed** |
| 67–69 | OAuth `content` | Sends `_SCOPE` to whichever token URL was set at construction | The scope string is the same for both environments; eBay grants or denies per keyset |
| 87–88 | `invalid_scope` handler | Raises `EbayAuthError` with message naming the environment and the scope | Correctly identifies which environment failed |
| 94–104 | `_invalid_scope_message()` | Generates actionable error message; explicitly says "Do not fall back to Browse API" |

**Sandbox vs. production distinction:** `EbayTokenManager` receives `environment` at construction from `config.ebay_environment`. Production and sandbox hit different base URLs. Scope is the same string for both — eBay's keyset configuration controls whether it is grantable.

**MI vs. Browse:** `_SCOPE` is `buy.marketplace.insights`. There is no Browse API scope string anywhere in this file or any other. No Browse fallback code exists.

**Credential-day flip:** changing `EBAY_ENVIRONMENT=sandbox` → `EBAY_ENVIRONMENT=production` in `.env` is a config-only change. No code change required.

---

### `src/zeal/ingestion/ebay_marketplace_insights_client.py` — live API client

| Line | Symbol | What it does |
|---|---|---|
| 24–27 | `_BASE_URLS` | Maps `"production"` → `https://api.ebay.com`; `"sandbox"` → `https://api.sandbox.ebay.com` |
| 28 | `_SEARCH_PATH` | `/buy/marketplace_insights/v1_beta/item_sales/search` — **Marketplace Insights endpoint only** |
| 29 | `_MARKETPLACE_ID` | `"EBAY_US"` — US-only; per spec |
| 30 | `_LOOKBACK_DAYS` | `90` |
| 105–109 | `__init__` | `self._base_url = _BASE_URLS[environment]` — sandbox vs. production correctly routed |
| 175–180 | `_get_with_retry()` GET | Adds `X-EBAY-C-MARKETPLACE-ID: EBAY_US` header; correct for Marketplace Insights |

**No Browse API references.** The search path `/buy/marketplace_insights/v1_beta/item_sales/search` is the Marketplace Insights item-sales endpoint. The Browse API path (`/buy/browse/v1/item_summary/search`) does not appear anywhere.

**Sandbox isolation:** `_base_url` is set at construction from the environment parameter, which flows from `config.ebay_environment`. A sandbox-configured client never hits `api.ebay.com`.

**Synthetic mode safety:** `EbayMarketplaceInsightsClient` is only constructed when `config.ebay_mode == "live"` (enforced in `ebay_client_factory.py:17–18`). In synthetic mode, `SyntheticEbayClient` is returned instead, which has no HTTP client and cannot make network calls.

---

### `src/zeal/ingestion/ebay_client.py` — protocol + synthetic client

| Line | Symbol | What it does |
|---|---|---|
| 9–19 | `EbayClient` Protocol | Structural protocol; no network code |
| 22–39 | `SyntheticEbayClient` | In-memory; reads from a dict; no `httpx`, no URL, no I/O of any kind |

**Synthetic mode cannot accidentally hit live endpoints.** `SyntheticEbayClient` has no HTTP client field, no URL, no `httpx` import.

---

### `src/zeal/ingestion/ebay_client_factory.py` — factory

| Line | Logic | Assessment |
|---|---|---|
| 17–18 | `if config.ebay_mode == "synthetic": return SyntheticEbayClient()` | Clean hard gate; returns no-network client |
| 20–21 | Checks `client_id` and `client_secret` not None | Belt-and-suspenders (config already validates this for live mode) |
| 23–34 | Constructs `EbayTokenManager` with `environment=config.ebay_environment`, then `EbayMarketplaceInsightsClient` | Environment correctly threaded through |

**No fallback to Browse API.** The factory returns either `SyntheticEbayClient` or `EbayMarketplaceInsightsClient`. There is no else branch for a Browse-based client.

---

### `src/zeal/ingestion/refresh.py` — refresh orchestrator

| Line | Relevance | Assessment |
|---|---|---|
| 76–78 | Calls `ebay_client.sold_listings_for_merchant(...)` | Calls through the Protocol; works for both synthetic and live |
| 72–73 | `if merchant.online_sell_override is not None: _process_override(...)` | Skips eBay fetch for override merchants (per architecture §12 Q4) |

No direct eBay URL or scope references. The client is injected. Clean.

---

### `src/zeal/web/app.py` — app lifespan wiring

| Line | What it does | Assessment |
|---|---|---|
| 33 | `config = ZealConfig.from_env()` | Re-reads env at startup; picks up `.env` changes on restart |
| 36 | `ebay_client = create_ebay_client(config=config, http_client=app.state.http_client)` | Factory call; returns synthetic or live |
| 37–38 | `if app.state.ebay_client_factory is app.state.default_ebay_client_factory: app.state.ebay_client_factory = lambda: ebay_client` | Preserves test-injected factory; replaces default factory with the config-derived client |
| 57 | `app.state.default_ebay_client_factory = lambda: SyntheticEbayClient()` | Safe fallback; the pre-lifespan state is always synthetic |

**Assessment:** Lifespan correctly replaces the default synthetic factory only if no test override is present. The `http_client` is shared and properly closed in `finally`.

---

### `src/zeal/web/routes/refresh.py` — refresh route

| Line | What it does | Assessment |
|---|---|---|
| 95–99 | `if request.app.state.zeal_config.ebay_mode == "synthetic": return HTMLResponse(409, ...)` | **Refresh is blocked in synthetic mode** — operator cannot trigger a live run accidentally |
| 115–119 | Creates background task; passes `request.app.state.ebay_client_factory` | Factory (not the client itself) is passed; each task invocation calls the factory fresh |

---

### `src/zeal/cli.py` — smoke-ebay command

| Line | What it does | Assessment |
|---|---|---|
| 50 | `load_dotenv()` | Reads `.env` before config read |
| 63 | Warns if `config.ebay_mode == "synthetic"` | Operator-visible warning; does not abort (synthetic smoke is valid for diagnostic) |
| 70–87 | `create_ebay_client(config=config, http_client=http_client, max_results_default=fetch_limit)` | Factory pattern; sandbox vs. production determined by env |

---

## 2. Browse API fallback — confirmed absent

```
grep -rn "browse\|Browse\|findCompletedItems\|buy/browse" src/zeal/ --include="*.py"
# Result: (no output)
```

No Browse API paths, method names, or endpoint strings exist in the codebase.

---

## 3. Synthetic mode safety — confirmed

`SyntheticEbayClient` has zero network dependencies. `create_ebay_client()` hard-gates on `config.ebay_mode`. The refresh route returns 409 if `ebay_mode == "synthetic"`. There is no code path through which synthetic mode can reach a live eBay endpoint.

---

## 4. OAuth scope centralization — **confirmed clean** (Phase 3 fix applied)

`_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"` is defined once in `ebay_oauth.py:11`. It is used in:
- `EbayTokenManager._fetch()` at line 69 (the OAuth POST body)
- `_invalid_scope_message()` at line 98 via `{_SCOPE}` interpolation (fixed in Phase 3)

**Phase 3 resolution:** The duplicate scope literal at line 95 (`scope = "https://..."`) was removed and replaced with a direct reference to `_SCOPE`. The scope string now exists in exactly one place.

**Current search result:**
```
grep -rn "buy.marketplace.insights" src/zeal/
# ebay_oauth.py:11:  _SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
# ebay_oauth.py:100: "buy.marketplace.insights is assigned to this keyset. Do not run the ..."
```

The line 100 mention is human-readable instruction text in the error message (not a code constant); no action needed. The scope string is centralized.

---

## 5. Credential-day flip: config-only changes required

| Action | Change type | Files touched |
|---|---|---|
| Set `ZEAL_EBAY_MODE=live` | `.env` only | None |
| Set `EBAY_CLIENT_ID=<real id>` | `.env` only | None |
| Set `EBAY_CLIENT_SECRET=<real secret>` | `.env` only | None |
| Set `EBAY_ENVIRONMENT=production` | `.env` only | None (default is already `production`) |
| Restart the dashboard | Operational step | None |

**No code change is required for credential-day.** The entire switch from synthetic to live mode, and from sandbox to production environment, is controlled through `.env` variables. The architecture correctly defers all these decisions to config.

---

## 6. Remaining items for live operation

- ~~**`_invalid_scope_message()` scope literal:** Use `_SCOPE` constant.~~ **RESOLVED in Phase 3.**
- ~~**Stale TODO at `web/routes/refresh.py:70`.**~~ **RESOLVED in Phase 3** — replaced with accurate comment.
- **No rate-limit budget configuration:** `per_call_sleep_ms=100` is hardcoded as a default in `EbayMarketplaceInsightsClient.__init__`. It is exposed as a constructor parameter, but `create_ebay_client()` does not pass it (100ms is always used). If the granted eBay tier requires different pacing, a code change (or adding a `EBAY_SLEEP_MS` env var) would be needed. Documented in `11_followups.md` #10. **Not blocking for credential day.**
