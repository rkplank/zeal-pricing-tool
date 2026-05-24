# Audit Report 07 — Test Coverage Gaps

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

This report lists route handlers, pricing functions, ingestion paths, and DB functions that have **no direct test**. Some are tested indirectly (through higher-level integration tests); those are flagged separately. No new tests are proposed here.

---

## 1. Route handlers

### Tested directly

| Route | Test file | Test name(s) |
|---|---|---|
| `GET /` | `test_web_routes.py:166` | `test_pricing_list_route_returns_200` |
| `GET /merchant/{id}` | `test_web_routes.py:194,242,256,318,329` | Multiple detail scenarios |
| `GET /merchant/{id}/config` | `test_web_routes.py:337` | `test_merchant_config_page_loads_with_percent_values` |
| `POST /merchant/{id}/config` (success) | `test_web_routes.py:356` | `test_merchant_config_save_updates_margin_and_history` |
| `POST /merchant/{id}/config` (blank override) | `test_web_routes.py:395` | `test_merchant_config_blank_nullable_override_stores_null` |
| `POST /merchant/{id}/config` (bad percent) | `test_web_routes.py:428` | `test_merchant_config_invalid_percentage_is_rejected` |
| `POST /merchant/{id}/config` (404) | `test_web_routes.py:402` | Unknown merchant → 404 behavior |
| `GET /refresh/status` (idle) | `test_refresh_routes.py:105` | `test_refresh_status_idle_no_runs` |
| `GET /refresh/status` (running) | `test_refresh_routes.py:116,130` | Running state scenarios |
| `GET /refresh/status` (transition) | `test_refresh_routes.py:145,182,209` | Completed/partial/failed transitions |
| `POST /refresh` (live mode) | `test_refresh_routes.py:227` | Starts background task |
| `POST /refresh` (conflict) | `test_refresh_routes.py:244,260,271` | Double-start prevention |

### Not directly tested

| Route | Gap |
|---|---|
| `POST /refresh` when `ebay_mode == "synthetic"` | `refresh.py:95–99` returns 409; the test at `test_refresh_routes.py:260` tests the 409 for a running refresh, but **not** the synthetic-mode early return. The synthetic-mode 409 is a separate code path that has no dedicated test. |
| `GET /merchant/{id}` 404 | `test_web_routes.py:484` (`test_missing_merchant_returns_404`) tests this. ✓ Covered. |

---

## 2. Pricing functions (`src/zeal/pricing/`)

### Tested

| Function | Test file |
|---|---|
| `compute_prices()` | `test_pricing_engine.py`, `test_pricing_engine_baseline.py` (281 golden records) |
| `blend_values()` | `test_pricing_blending.py` |
| `score_confidence()` | `test_confidence.py` |
| `compute_ebay_average()` | `test_ebay_average.py` |
| `filter_listings()` | `test_listing_filter.py` |
| `aggregate_competitor_observations()` | `test_competitor_aggregate.py` |

### Not directly tested

| Function | Location | Gap |
|---|---|---|
| `_compute_online_sell_ebay()` | `engine.py:78` | Private helper; covered indirectly via `compute_prices()` golden tests. No isolated unit test. |
| `_compute_in_mail_ebay()` | `engine.py:89` | Same. |
| `_compute_in_store_ebay()` | `engine.py:107` | Same. |
| `_compute_electronic_ebay()` | `engine.py:125` | Same. |
| `_compute_electronic_competitor()` | `engine.py:139` | Same. No direct test for the `competitor.in_mail_buy - competitor_electronic_markdown` fallback path. |
| `_channel_result()` | `engine.py:155` | Private; tested indirectly. The `ebay_only_due_to_missing_competitor_data` path (competitor is None but eBay value is valid) has no dedicated case in `test_pricing_engine.py`. |
| `_online_sell_steps()` | `engine.py:197` | Breakdown steps tested via `formula_breakdown_json` in golden tests, but not isolated. |
| `_in_mail_steps()`, `_in_store_steps()`, `_electronic_steps()` | `engine.py:215–281` | Same as above. |
| `_classify()` | `listing_filter.py:61` | Private; covered via `filter_listings()` tests. |
| `_is_valid()`, `_weighted_average()`, `_parse_datetime()` | `competitor_aggregate.py:59–79` | Private; covered via `aggregate_competitor_observations()` tests. |

**Assessment:** private engine helper functions are adequately covered through golden tests. The biggest gap is `_compute_electronic_competitor()` — the path `competitor.in_mail_buy - competitor_electronic_markdown` (lines 151–152) is exercised by `test_competitor_aggregate.py` and `test_pricing_engine.py` but only in combination. No test isolates the fallback-to-in_mail path specifically.

---

## 3. DB repository functions (`src/zeal/db/repositories.py`)

### Tested directly

| Function | Test file |
|---|---|
| `fetch_pricing_list()` | `test_repositories.py:24` (list query + delta helpers) |
| `fetch_recommendation_history()` | `test_repositories.py:91` (indirectly via detail query) |
| `delta_from_prior()` | `test_repositories.py:35,44` |
| `max_absolute_delta_over_window()` | `test_repositories.py:44` |
| `fetch_merchant_detail()` | `test_repositories.py:91` |
| `fetch_merchant_config()` | `test_web_routes.py:337` (via config form route) |
| `update_merchant_config()` | `test_web_routes.py:356` (via config save route) |

### Not directly tested

| Function | Location | Gap |
|---|---|---|
| `fetch_pricing_list_summary()` | `repositories.py:181` | Called in `dashboard.py:17`; indirectly exercised by `test_pricing_list_route_returns_200`. No isolated test verifying the SQL aggregation logic, e.g., correct counting of `no_data`, `with_recommendation`, `live_ebay_observations`. |
| `_latest_refresh_status()` | `repositories.py:483` | Private; called from `fetch_pricing_list()`; no isolated test. |
| `_has_live_ebay_observations()` | `repositories.py:490` | Private; tested indirectly via `test_repositories.py:91` (detail query includes `has_live_ebay_observations`). |
| `_fetch_competitor_observations()` | `repositories.py:542` | Private; tested indirectly via detail query. No test verifies the 20-row limit or the ORDER BY ordering. |
| `_fetch_recent_refreshes()` | `repositories.py:570` | Private; tested indirectly via detail query. No test verifies the 10-run LIMIT or the LEFT JOIN producing `has_recommendation = False` when no recommendation exists for a run. |
| `_normalized_config_value()` | `repositories.py:398` | Private; no direct test. The `round(value, 12)` logic for float comparison is untested in isolation. |

---

## 4. Ingestion functions (`src/zeal/ingestion/`)

### Tested directly

| Function/class | Test file |
|---|---|
| `EbayTokenManager.get_access_token()` | `test_ebay_oauth.py` |
| `EbayTokenManager.force_refresh()` | `test_ebay_oauth.py` |
| `EbayTokenManager._fetch()` — success, 401, 4xx, 5xx paths | `test_ebay_oauth.py` |
| `EbayMarketplaceInsightsClient.sold_listings_for_merchant()` | `test_ebay_marketplace_insights_client.py` |
| `EbayMarketplaceInsightsClient._get_with_retry()` — retry paths | `test_ebay_marketplace_insights_client.py` |
| `extract_face_value()` | `test_ebay_marketplace_insights_client.py` |
| `create_ebay_client()` | `test_ebay_client_factory.py` |
| `run_refresh()` | `test_refresh_orchestrator.py` |
| `SyntheticEbayClient.sold_listings_for_merchant()` | `test_refresh_orchestrator.py` (implicitly) |

### Not directly tested

| Function | Location | Gap |
|---|---|---|
| `_process_override()` | `refresh.py:139` | Called when `merchant.online_sell_override is not None`. `test_refresh_orchestrator.py` tests the override path via `run_refresh()`, but no test inspects `_process_override()` in isolation. |
| `_persist_observations()` | `refresh.py:200` | Tested indirectly; the ON CONFLICT upsert logic (lines 215–225) has no isolated test verifying that a duplicate `listing_id` updates existing fields rather than inserting a new row. |
| `_insert_recommendation()` | `refresh.py:240` | Tested indirectly; no test verifies that `_num()` correctly returns `None` for non-numeric types. |
| `_row_to_merchant()` | `refresh.py:287` | Tested only indirectly (called by `run_refresh()`). No test feeds a raw `sqlite3.Row` directly. |
| `_load_merchant()` in `cli.py` | `cli.py:113` | No test calls `_load_merchant()` directly. Covered by `test_smoke_ebay_cli.py` at the CLI level (argument parsing, not row-mapping). |
| `_query_from_regex()` | `ebay_marketplace_insights_client.py:52` | Not tested directly. Covered indirectly through `sold_listings_for_merchant()` mock tests. Edge cases (e.g., regex with trailing `.*` or complex alternations) are not exercised. |
| `_parse_item()` | `ebay_marketplace_insights_client.py:63` | Not tested directly. Covered via mock API response fixtures in `test_ebay_marketplace_insights_client.py`. Missing items or unexpected field shapes are not tested in isolation. |
| `_safe_url()` | `ebay_marketplace_insights_client.py:80` | Not tested directly. Covered via `_parse_item()` indirect path. The `javascript:` scheme rejection is not explicitly tested. |

---

## 5. Web helpers (`src/zeal/web/routes/merchant.py`)

| Function | Test coverage |
|---|---|
| `build_price_history_chart()` | Tested in `test_web_routes.py:229,252,263,276,288,325` — good coverage |
| `_chart_domain()` | Indirectly via `build_price_history_chart()` |
| `_build_chart_series()` | Indirectly; the `len(current) >= 2` gap-segment logic is tested via `test_web_routes.py:288` |
| `_chart_value()` | Indirectly |
| `_chart_x()`, `_chart_y()` | Indirectly |
| `_parse_config_form()` | Tested via route POST tests |
| `_parse_percent()` (fraction input detection) | `test_web_routes.py:428` tests bad percentage; the "fraction-like value" branch (`0 < percent <= 1`) at `merchant.py:428–429` may not be explicitly tested. Needs confirmation. |
| `_parse_urlencoded_form()` | Indirectly via POST tests |

---

## 6. Template filters (`src/zeal/web/templating.py`)

| Filter | Test file |
|---|---|
| `_format_pct()` | `test_template_filters.py` |
| `_format_pp()` | `test_template_filters.py` |
| `_format_channel()` | `test_template_filters.py` |
| `_format_confidence()` | `test_template_filters.py` |
| `_format_datetime()` | `test_template_filters.py` |
| `_format_step_label()` | `test_template_filters.py` |
| `_is_status_step()` | `test_template_filters.py` |

All template filters are directly tested. Good coverage here.

---

## 7. Summary: highest-priority gaps

| Gap | Risk if untested |
|---|---|
| `POST /refresh` in synthetic mode (409 path) | Regression: synthetic-mode refresh block could silently stop working |
| `fetch_pricing_list_summary()` SQL aggregation | Wrong counts displayed to operator; hard to detect without a direct test |
| `_persist_observations()` ON CONFLICT upsert | Duplicate listings could corrupt observation history |
| `_query_from_regex()` edge cases | Bad eBay queries at live time; only caught on credential day |
| `_safe_url()` scheme rejection | Malformed URLs could be stored in DB |
| `_parse_percent()` fraction-input branch | Operator could save `0.85` as `0.0085` — silent pricing error |
