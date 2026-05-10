# Audit Report 14 — eBay Readiness Code Changes

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

---

## Summary

**No code changes were required in Phase 4** to make credential day config-only.

The path from "production keyset gains `buy.marketplace.insights`" to "live data
flowing" requires only `.env` changes and a dashboard restart. Every relevant
code path — OAuth scope, environment routing, client selection, refresh gating,
error propagation — was already correctly implemented.

---

## Phase 3 changes that improved readiness (already landed)

One code change made in Phase 3 directly improved credential-day readiness:

### `src/zeal/ingestion/ebay_oauth.py` — scope constant de-duplicated

**What changed:** `_invalid_scope_message()` previously re-stated the Marketplace
Insights scope as a string literal on line 95. It now references the module
constant `_SCOPE` instead.

**Before (Phase 3):**
```python
def _invalid_scope_message(environment: str, description: str) -> str:
    scope = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
    env_label = ...
    return f"... {scope} ..."
```

**After (Phase 3):**
```python
def _invalid_scope_message(environment: str, description: str) -> str:
    env_label = ...
    return f"... {_SCOPE} ..."
```

**Why this matters for credential day:** The scope string is now defined in
exactly one place. If eBay ever revisions the Marketplace Insights scope name
(e.g., from `v1_beta` to `v1`), there is one line to update and the error
message automatically reflects it.

---

## Confirmation: credential-day flip is config-only

The following table confirms which actions are needed to go from current synthetic
state to live data flowing, and that none require source code changes:

| Action | Type | Files affected |
|---|---|---|
| Set `ZEAL_EBAY_MODE=live` | `.env` edit | None |
| Set `EBAY_CLIENT_ID=<production id>` | `.env` edit | None |
| Set `EBAY_CLIENT_SECRET=<production secret>` | `.env` edit | None |
| Confirm `EBAY_ENVIRONMENT=production` (already default) | `.env` confirm | None |
| Restart dashboard | Operational | None |
| Run `uv run python -m zeal.cli smoke-ebay --merchant home_depot --limit 10` | Validation | None |

**No source code, schema, test, or config file changes are needed for credential day.**
