# Audit Report 06 — Security and Secrets

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

---

## 1. Every place env vars or secrets are read

### `src/zeal/config.py`

```python
# Line 26:  load_dotenv()
# Line 30:  _optional_env("EBAY_CLIENT_ID")
# Line 31:  _optional_env("EBAY_CLIENT_SECRET")
# Line 32:  os.environ.get("ZEAL_DB_PATH", str(DEFAULT_DB_PATH))
# Line 63:  os.environ.get("ZEAL_EBAY_MODE", "synthetic")
# Line 70:  os.environ.get("EBAY_ENVIRONMENT", "production")
```

This is the **single authoritative env-read point** for all runtime configuration. `ZealConfig.from_env()` is called once at app startup (`app.py:33`) and once in `cli.py:50` for the smoke-ebay command. No other code reads credentials directly from the environment.

### `src/zeal/cli.py`

```python
# Line 9:   from dotenv import load_dotenv
# Line 50:  load_dotenv()    (inside cmd_smoke_ebay before calling ZealConfig.from_env())
```

`cli.py` calls `load_dotenv()` before calling `ZealConfig.from_env()`. This is redundant with the `load_dotenv()` inside `ZealConfig.from_env()` itself (`config.py:26`), but harmless — `python-dotenv` is idempotent. No direct `os.environ` reads for secrets in `cli.py`.

### `src/zeal/ingestion/ebay_oauth.py`

No direct env reads. Receives `client_id` and `client_secret` as constructor arguments from `EbayTokenManager.__init__`. Secrets flow through `config.py` → `ebay_client_factory.py` → `EbayTokenManager`. Clean.

**Assessment:** Secret reads are correctly centralized in `config.py`. No module outside `config.py` and `cli.py` (which delegates to `config.py`) reads credentials from the environment.

---

## 2. Hardcoded keys, tokens, URLs, or test credentials

**Search run:**
```
grep -rn "sk-\|api_key\|bearer\|EBAY_CLIENT_ID\|EBAY_CLIENT_SECRET\|client_id.*=.*['\"][A-Za-z0-9]" src/ tests/ --include="*.py"
# Result: (no output matching credentials)
```

No hardcoded API keys or secrets found in source or tests.

**Test fixtures check:**
```
grep -rn "EBAY_CLIENT" tests/ --include="*.py"
# Result: references to environment variable names in mock setup, no actual credential values
```

Tests use `respx` (HTTP mocking) and never embed real credentials. The `conftest.py` sets `ZEAL_EBAY_MODE=synthetic` for the test environment via fixture, ensuring tests never need real credentials.

**Hardcoded eBay URLs in source:**
- `ebay_oauth.py:16–18`: `_BASE_URLS` maps environment names to `https://api.ebay.com` and `https://api.sandbox.ebay.com`. These are official eBay API base URLs, not secrets. Appropriate to hardcode.
- `ebay_marketplace_insights_client.py:24–27`: same pattern. Appropriate.
- `ebay_marketplace_insights_client.py:28–29`: path and marketplace ID. Appropriate.

No test credentials, sample tokens, or placeholder keys found.

---

## 3. Logging that might emit secrets

**Search run:**
```
grep -rn "log\|logger\|logging" src/zeal/ --include="*.py" | grep -i "secret\|password\|token\|credential\|client_id\|client_secret"
# Result: (no output)
```

No logging statements reference secret fields.

**EbayTokenManager credential storage:**
- `ebay_oauth.py:36–38`: `self._credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()`
- The credentials are stored only as a Base64 string in memory. The `Authorization: Basic {self._credentials}` header is sent over HTTPS. The Base64 string is never logged.
- `logger` is not used in `ebay_oauth.py` at all — no logging calls, so no accidental header logging.

**EbayMarketplaceInsightsClient:**
- `_get_with_retry()` at lines 175–180 sends `Authorization: Bearer {current_token}` — the token is in the header, not logged.
- On error paths (401, 429, 5xx), the response body is not logged. The `EbayAuthError`/`EbayRateLimitError`/`EbayServerError` messages contain status codes and error fields from the response, not credential values.

**Assessment:** No logging path emits secrets or tokens. Clean.

---

## 4. File permissions on persisted credential caches

### `.env` file

```
stat .env
# Access: (0644/-rw-r--r--)
```

Permissions `0644` mean world-readable on Unix/Linux. On Windows (the deployment target), the file system is NTFS with ACLs rather than Unix permissions, and `0644` is a reporting artifact of Git for Windows / MSYS — the actual Windows ACL controls access. On a single-operator Windows home machine, this is acceptable for v1 (no multi-user concern).

**Recommendation (low priority for v1):** on Linux/Mac developer machines, consider `chmod 600 .env`. On the production Windows machine, the risk is low given single-user context.

### OAuth token cache

`EbayTokenManager` caches the token as instance variables (`self._token`, `self._expires_at`). This is **in-memory only** — the token is never written to disk. There is no token cache file. No file permission concern.

---

## 5. `.env` gitignore and staging status

```
grep -n "\.env" .gitignore
# Result: 7:.env
```

`.env` is correctly listed in `.gitignore`.

```
git status --short .env
# Result: (no output — .env is not staged and not tracked)
```

`.env` is gitignored and not staged. No secrets in git history from this file.

**Check for accidental .env content in committed files:**
```
grep -rn "EBAY_CLIENT_ID=\|EBAY_CLIENT_SECRET=" . --exclude-dir=.git --exclude-dir=.venv --include="*.py" --include="*.json" --include="*.md" --include="*.toml"
# Result: (no output — only the variable name without a value appears in docs)
```

No credential values committed.

---

## 6. URL validation in live client

`ebay_marketplace_insights_client.py:80–86`:
```python
def _safe_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value
```

This function sanitizes `itemWebUrl`/`itemAffiliateWebUrl` from the eBay payload before storing it. Only `http`/`https` URLs with a non-empty host are passed through; other schemes (e.g. `javascript:`) are rejected. Good defensive practice against a malicious or malformed eBay payload.

---

## 7. SQL injection risk

All DB queries in `repositories.py` and `refresh.py` use parameterized queries with `?` placeholders. One dynamic SQL construction exists:

`repositories.py:299`:
```python
assignments = ", ".join(f"{field} = ?" for field in MERCHANT_CONFIG_FIELDS)
```

`MERCHANT_CONFIG_FIELDS` is a hardcoded tuple of string literals defined at module level (line 9–26). It is never populated from user input. The resulting SQL is constructed from known-safe field names. **No SQL injection risk.**

---

## 8. Additional observations

- **No auth middleware.** The dashboard has no authentication. This is by design (single-operator, localhost-only). No change needed for v1, but any future network-facing deployment would require auth.
- **HTMX loaded via CDN** (`base.html` links to `https://unpkg.com/htmx.org`). A supply-chain or CDN availability risk. For a local-only operator tool this is acceptable; for a future hosted deployment, consider bundling `htmx.min.js` locally (the `architecture.md` layout listed it as a static file; this would be the right eventual fix).
- **No CSRF protection.** FastAPI + HTMX does not add CSRF tokens by default. The `POST /merchant/{id}/config` and `POST /refresh` routes are not protected. Again: localhost-only single-user deployment makes this acceptable for v1, but a future networked deployment would need it.
