# Audit Report 10 — Bugs and Quality Issues To Review

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

These are findings from `04_code_quality_findings.md` that were not fixed in
Phase 3 because: (a) they require a decision, (b) they touch multiple files
and the fix is not "clearly local," or (c) they need live-mode validation before
a fix is justified.

---

## BUG-01 — `_row_to_merchant()` duplicated between `refresh.py` and `cli.py`

**File:line:**  
- `src/zeal/ingestion/refresh.py:287-319`  
- `src/zeal/cli.py:113-157`

**Description:** Both functions map a `sqlite3.Row` to `MerchantRecord` with
identical field-by-field mappings. They were audited and confirmed to be
functionally identical (the earlier claim about `merch_credit_variant` being
omitted from `cli.py` was incorrect — both include it). The duplication is a
maintenance hazard: if a schema column is added to `merchants`, both mappings
must be updated independently.

**Proposed fix:** Extract `_row_to_merchant()` from `ingestion/refresh.py` into
`src/zeal/db/repositories.py` as a module-level function, and call it from both
`refresh.py` and `cli.py`. Risk: low, but touches three files simultaneously and
requires careful import ordering (repositories ← ingestion, not the reverse, to
avoid circular imports). `cli.py` imports from `db.connection` already, so
importing from `db.repositories` is clean.

**Risk:** Low. No behavioral change; pure refactor. Recommend addressing in a
dedicated PR after Phase 3.

---

## BUG-02 — `type: ignore[operator]` in `web/routes/refresh.py:71`

**File:line:** `src/zeal/web/routes/refresh.py:71`

```python
ebay_client = ebay_client_factory()  # type: ignore[operator]
```

**Description:** `app.state.ebay_client_factory` is typed as `object` because
FastAPI's `State` is untyped. The suppression is narrow and correct, but it
hides the fact that the factory's return type is not statically verified.

**Proposed fix:** Type `app.state` entries via a typed `AppState` class or use
`cast()` at the call site. FastAPI does not natively support typed `app.state`
without a wrapper. Alternatively, store the factory as a typed protocol
attribute on a custom subclass of `FastAPI`. Requires changes to `app.py` and
all tests that set `request.app.state.*`.

**Risk:** Medium. Correct behavior is unchanged; this is a type-safety
improvement. Leave for a v2 cleanup sprint.

---

## BUG-03 — `fetch_pricing_list_summary()` aggregation not directly tested

**File:line:** `src/zeal/db/repositories.py:181`

**Description:** The SQL aggregation in `fetch_pricing_list_summary()` computes
`no_data`, `with_recommendation`, and `live_ebay_observations` counts. These are
surfaced on the dashboard header. A wrong count (e.g., off-by-one in the DISTINCT
count or a miscounted `no_data` merchant) would be operator-visible. The function
is only tested indirectly via the route test at `test_web_routes.py:166`, which
verifies a 200 response but does not assert specific count values.

**Proposed fix:** Add a direct unit test in `test_repositories.py` that seeds
specific merchant/recommendation combinations (e.g., 2 with data, 1 no_data, 1
with live observation) and asserts the exact summary values.

**Risk of fix:** Low. Test-only change; no production code touched.

---

## BUG-04 — `_persist_observations()` ON CONFLICT upsert not isolated

**File:line:** `src/zeal/ingestion/refresh.py:200`

**Description:** The `ON CONFLICT(listing_id) DO UPDATE SET ...` upsert at line
209 updates all observation fields when a listing is re-fetched. No test verifies
that a duplicate `listing_id` updates the existing row rather than failing or
silently discarding. The schema constraint prevents duplicates, but the updated
field values after an upsert are not tested.

**Proposed fix:** Add a test that calls `_persist_observations()` twice with the
same `listing_id` but different field values, then asserts the second set of
values is in the DB.

**Risk of fix:** Low. Test-only change in most implementations. Requires
exposing `_persist_observations()` to tests (currently private) or testing
indirectly via `run_refresh()` with a controlled `SyntheticEbayClient`.

---

## ~~BUG-05 — `_parse_percent()` fraction-input guard not directly tested~~

**Resolved 2026-05-10 by `tests/test_web_routes.py::test_merchant_config_percent_field_accepts_human_format_and_rejects_fractions`**

**Note on audit finding:** The original claim that `test_merchant_config_invalid_percentage_is_rejected`
"only tests fully invalid input (e.g., letters)" was incorrect — that test
already tested `"0.85"` rejection. What was genuinely missing was explicit
coverage of the acceptance path ("85", "85.0", "85%"). The new test pins both
sides: acceptance (303 redirect + stored as 0.85) and rejection (400 + error text).

---

## ~~BUG-06 — `POST /refresh` synthetic-mode 409 not tested~~

**Resolved — already covered by `tests/test_refresh_routes.py::test_post_refresh_in_synthetic_mode_is_blocked` (line 265)**

**Note on audit finding:** The original claim that this was not covered was incorrect.
The existing test (added before the audit) already pins all three requirements:
status 409, body text "Refresh is disabled in synthetic mode", and no new
`refresh_runs` row created (`before["id"] == after["id"]`). No new test added.

---

## Notes

- BUG-01 through BUG-06 are all quality/coverage issues, not correctness bugs in
  the current code.
- No pricing formula errors, no algorithm bugs, and no correctness regressions
  were identified in Phase 3.
- BUG-05 carries the highest operator-visible risk if it regresses; it should be
  addressed first.
