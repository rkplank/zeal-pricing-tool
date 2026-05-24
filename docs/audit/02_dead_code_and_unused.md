# Audit Report 02 — Dead Code and Unused Symbols

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

All claims backed by `rg` (ripgrep / `grep -rn`) searches run during the audit session.

---

## Definitely Unused

### 1. `src/zeal/jobs/__init__.py` — entire file

File is one blank line. No imports, no exports.

**Search run:**
```
grep -rn "zeal.jobs\|from zeal.jobs\|import jobs" src/ tests/
# Result: (no output)
```

Nothing in the package or test suite imports from `zeal.jobs`. The module exists solely as a structural placeholder per `architecture.md` §3 ("placeholder; v1 has no scheduled jobs"). File is harmless but adds surface area.

---

### 2. `src/zeal/models/ebay.py` — `EbaySummary` class (lines 30–37)

`EbaySoldListing` and `EbayObservation` are used throughout. `EbaySummary` is defined but never instantiated.

**Search run:**
```
grep -rn "EbaySummary" src/ tests/
# Result: src/zeal/models/ebay.py:30:class EbaySummary(BaseModel):
```

Only the definition itself matches. No constructor call, no import of `EbaySummary`, no type annotation using it.

The DB schema has an `ebay_summary` table and `refresh.py` writes to it via raw SQL (`INSERT OR REPLACE INTO ebay_summary ...`). The Pydantic model is never used to represent that data. The `EbaySummary` class is a definition without a consumer.

---

### 3. `src/zeal/models/competitor.py` — `CompetitorSource` class (lines 11–19)

`CompetitorObservation` is used (in `pricing/competitor_aggregate.py` and `db/repositories.py`). `CompetitorSource` is not.

**Search run:**
```
grep -rn "CompetitorSource" src/ tests/
# Result: src/zeal/models/competitor.py:11:class CompetitorSource(BaseModel):
```

Only the definition matches. The `competitor_sources` DB table is populated by `db/seed.py` via raw SQL; the `CompetitorSource` Pydantic model is never instantiated in that path. No route, test, or helper uses the class.

---

### 4. Stale TODO comment — `src/zeal/web/routes/refresh.py:70`

```python
# TODO: replace SyntheticEbayClient with the real Marketplace Insights client
ebay_client = ebay_client_factory()  # type: ignore[operator]
```

**Search run:**
```
grep -rn "TODO\|FIXME\|HACK\|XXX" src/zeal/
# Result: src/zeal/web/routes/refresh.py:70
```

The TODO is stale. The factory mechanism it describes is already implemented: `app.py` wires `ebay_client_factory` at startup via `create_ebay_client(config=config, ...)`, which returns `EbayMarketplaceInsightsClient` when `ZEAL_EBAY_MODE=live`. The code on the next line already calls the factory correctly. There is no code change required here — only a `.env` flip. The comment implies a code change that does not need to happen, which could mislead a future developer.

---

### 5. Garbled artifact directory — `c:devzeal-pricing-toolscripts/`

**Search run:**
```
ls "c:devzeal-pricing-toolscripts/"
# Result: (empty)
```

Directory is empty and has a garbled name (a prior Bash session misinterpreted a Windows path). It serves no purpose and is not referenced anywhere.

---

## Possibly Unused — Needs Human Eyes

### 6. `_mode_context()` — identical function duplicated in three route files

**Search run:**
```
grep -n "_mode_context" src/zeal/web/routes/dashboard.py src/zeal/web/routes/merchant.py src/zeal/web/routes/refresh.py
# Result:
#   dashboard.py:27:    **_mode_context(request),
#   dashboard.py:32:def _mode_context(request: Request) -> dict[str, object]:
#   merchant.py:101:    **_mode_context(request),
#   merchant.py:147:def _mode_context(request: Request) -> dict[str, object]:
#   merchant.py:307:    **_mode_context(request),
#   refresh.py:162:    **_mode_context(request),
#   refresh.py:174:def _mode_context(request: Request) -> dict[str, object]:
```

Each file defines an identical private function (6 lines, identical body). Not dead code, but duplicated code. If the context keys ever need changing (e.g., adding `ebay_environment` to template context), all three copies must be updated. Consolidation into `web/templating.py` or a shared `web/routes/_context.py` would prevent drift. Not strictly dead, but a maintenance hazard.

---

### 7. Template filters — `_format_channel` labels for non-dashboard channels

**Search run:**
```
grep -rn "buy_mail\|buy_electronic\|marketplace_sell" src/zeal/web/templates/
# Result: (no output)
```

The `_format_channel` filter in `web/templating.py` (lines 66–77) maps `"buy_mail"`, `"buy_electronic"`, `"sell"`, and `"marketplace_sell"` to display strings. These are `competitor_observations.channel` values. Whether they are actually reached through the competitor panel template depends on whether `competitor_panel.html` uses the `channel` filter. The competitor panel does display channel data, so these labels are reachable — but only when competitor observations exist. Worth confirming the template applies the filter correctly during a live run.

---

### 8. `MerchantListRow.has_live_ebay_observations` field

**Search run:**
```
grep -rn "has_live_ebay_observations\|live_ebay_observations" src/zeal/ templates/ tests/ 2>/dev/null
# Result: repositories.py (definition, query), test_repositories.py, dashboard template
```

This is used; surfaced in `PricingListSummary.live_ebay_observations` counter and the dashboard badge. Not dead. Noted here because the badge is currently always 0 in synthetic mode — any template test that checks for a non-zero value has never been exercised against live data.

---

## Confirmed NOT Dead (searched and verified)

- All four pricing engine channel functions (`_compute_online_sell_ebay`, etc.): called by `compute_prices()`, which is tested by 493 passing tests.
- `SyntheticEbayClient`: used by app lifespan, factory, and tests.
- `EbayMarketplaceInsightsClient`: used by factory; not dead just because live mode is blocked.
- `aggregate_competitor_observations()` in `competitor_aggregate.py`: used by tests; structurally available to refresh path once competitor scraper is built.
- `blend_values()`: called by `engine.py`; tested.
- All template filter functions in `templating.py`: registered via `configure_template_filters()` and used by templates.
