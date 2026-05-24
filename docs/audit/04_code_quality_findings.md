# Audit Report 04 — Code Quality Findings

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

---

## 1. `ruff check . --statistics`

```
uv run ruff check . --statistics
# Result: (no output — all checks passed)
```

**Result: PASS. Zero warnings. Zero errors.**

Ruff is clean across all 34 source files.

---

## 2. `mypy src` summary

```
uv run mypy src
# Result: Success: no issues found in 34 source files
```

**Result: PASS. No type errors.**

One noteworthy mypy suppression in production code:

- `src/zeal/web/routes/refresh.py:71`: `ebay_client = ebay_client_factory()  # type: ignore[operator]`
  
  The `type: ignore` is needed because `app.state.ebay_client_factory` is stored as `object` on `app.state` (FastAPI's `State` is untyped). The suppression is narrow and correctly scoped. The factory always returns an `EbayClient`-protocol-compatible object. Acceptable but worth tracking — if `app.state` were typed, this suppression could be removed.

---

## 3. `pytest -q` final summary

```
uv run pytest -q
# 493 passed in 8.31s
```

**Result: PASS. 493 passed, 0 failed, 0 skipped, 0 xfail.**

No skipped tests, no expected failures. The entire suite is green.

---

## 4. TODO / FIXME / HACK / XXX comments

```
grep -rn "TODO\|FIXME\|HACK\|XXX" src/zeal/ --include="*.py"
# Result:
#   src/zeal/web/routes/refresh.py:70:        # TODO: replace SyntheticEbayClient with the real Marketplace Insights client
```

**One TODO found. It is stale.**

`src/zeal/web/routes/refresh.py:70`:
```python
async def _run_in_background(db_path: Path, ebay_client_factory: object) -> None:
    conn = get_connection(db_path)
    try:
        constants = _load_constants(conn)
        # TODO: replace SyntheticEbayClient with the real Marketplace Insights client
        ebay_client = ebay_client_factory()  # type: ignore[operator]
```

The mechanism the TODO describes is already implemented. The `ebay_client_factory` argument is wired in `app.py` via `create_ebay_client()`, which returns `EbayMarketplaceInsightsClient` when `ZEAL_EBAY_MODE=live`. No code change is required — only a `.env` change. The comment is misleading: it implies a code action that does not need to happen.

**Recommended fix (docs phase, not this phase):** Remove the comment or replace it with: `# Factory returns SyntheticEbayClient or EbayMarketplaceInsightsClient per ZEAL_EBAY_MODE.`

---

## 5. `print()` calls in `src/zeal/`

```
grep -rn "print(" src/zeal/ --include="*.py"
# Result: all in src/zeal/cli.py, lines 26, 37, 59, 63, 67, 83, 91–96, 102–107, 109
```

All `print()` calls are in `src/zeal/cli.py`. This is intentional: the CLI is an operator-facing terminal tool where `print()` is the correct output mechanism (the user runs `zeal smoke-ebay` and reads stdout). Using `logging` in the CLI would route output through the logging framework and add timestamps/levels that are not appropriate for user-facing terminal output.

**Assessment:** acceptable as-is. `cli.py` is a CLI tool, not a library module. No action needed.

No `print()` calls exist in `db/`, `ingestion/`, `pricing/`, `web/`, or `models/`. Those modules correctly use `logging.getLogger(__name__)`.

---

## 6. Bare `except:` and `except Exception:` handlers

```
grep -rn "except:" src/zeal/ --include="*.py"
# Result: (no output — no bare except:)

grep -rn "except Exception" src/zeal/ --include="*.py"
# Result:
#   src/zeal/ingestion/refresh.py:79:    except Exception:
#   src/zeal/ingestion/refresh.py:118:    except Exception as exc:
#   src/zeal/ingestion/refresh.py:129:    except Exception:
#   src/zeal/web/routes/refresh.py:82:    except Exception:
```

All four are in the refresh path. All four are **correctly handled** — none swallow silently:

| Location | Pattern | Disposition |
|---|---|---|
| `ingestion/refresh.py:79` | `except Exception:` | `logger.exception(...)` immediately follows; merchant_id and run_id logged; merchant is added to `errored` list and refresh continues |
| `ingestion/refresh.py:118` | `except Exception as exc:` | marks `refresh_runs` row as `failed` with error text; then `raise` re-raises |
| `ingestion/refresh.py:129` | `except Exception:` | `logger.exception(...)` on the inner "mark as failed" attempt; then outer `raise` proceeds |
| `web/routes/refresh.py:82` | `except Exception:` | `logger.exception(...)` in the background task wrapper; finally block closes DB connection |

The broad catches are justified: the refresh loop processes ~300 merchants across external API calls and DB writes, and a single unexpected exception type should not silently abort the whole run. All four handlers log with `logger.exception()` (which captures the full traceback). **No swallowing without logging.** No action needed.

---

## 7. Copy-paste duplication >15 lines

### `_mode_context()` — triplicated across route files

**Search run:**
```
grep -n "_mode_context" src/zeal/web/routes/dashboard.py \
                        src/zeal/web/routes/merchant.py \
                        src/zeal/web/routes/refresh.py
```

Identical 6-line function defined in three files:

```python
# dashboard.py:32-38, merchant.py:147-153, refresh.py:174-180 — all identical:
def _mode_context(request: Request) -> dict[str, object]:
    config = request.app.state.zeal_config
    is_synthetic = config.ebay_mode == "synthetic"
    return {
        "ebay_mode_label": "Synthetic" if is_synthetic else "Live eBay",
        "is_synthetic_mode": is_synthetic,
    }
```

6 lines × 3 files = 18 lines of identical code. Not above the 15-line threshold individually, but the triplication is structural. If a new context key is needed (e.g., `ebay_environment` for a "Sandbox" badge), all three copies must be updated consistently.

**Recommended fix (code phase):** move `_mode_context()` to `web/templating.py` or a shared `web/routes/_shared.py` and import it in all three route modules.

---

### `_row_to_merchant()` — duplicated between `ingestion/refresh.py` and `cli.py`

`ingestion/refresh.py:287-319` and `cli.py:113-157` both construct `MerchantRecord` from a `sqlite3.Row`. The logic is identical (field-by-field mapping with `None` guards for nullable columns). The `cli.py` version omits `merch_credit_variant` read vs. the refresh version — a subtle divergence that could cause a bug if the schema changes.

**Search run:**
```
grep -n "_row_to_merchant\|MerchantRecord(" src/zeal/ingestion/refresh.py src/zeal/cli.py
# refresh.py:287: def _row_to_merchant(row: sqlite3.Row) -> MerchantRecord:
# cli.py:130:     return MerchantRecord(
```

`cli.py` does not call `_row_to_merchant()` from `refresh.py`; it re-implements the same mapping inline. The `_load_merchant()` function in `cli.py` (lines 113–157) is ~28 lines of duplicated row-mapping code with the same `None` guards. This is a maintenance hazard: if the schema adds a column, the DB queries in `refresh.py:_row_to_merchant()` and `cli.py:_load_merchant()` must both be updated, and there is no test that exercises `_load_merchant()` directly against the real schema.

**Recommended fix (code phase):** extract `_row_to_merchant()` from `refresh.py` into `db/repositories.py` (or make it accessible) and call it from `cli.py`.

---

## 8. Other minor observations

- **`ingestion/refresh.py:251`**: `ebay_client_factory()` is typed as `object` via `type: ignore[operator]`, consistent with the `app.state` typing limitation. The `type: ignore` in `web/routes/refresh.py:71` is the same root cause.
- **`db/seed.py:DEMO_CONSTANTS`**: `competitor_electronic_markdown` is not set, so the Pydantic default `0.05` applies. This is intentional (the field has a model default) but is not explicitly documented in the seed. Low risk.
- **No `__all__` exports defined** in any module. Not an issue for a single-application codebase (no public library surface), but a future consumer of `zeal.pricing` would need to discover exports by inspection.
