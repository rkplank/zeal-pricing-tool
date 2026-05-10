# Audit Report 09 — Uncertain Exception Handlers

**Audit date:** 2026-05-10  
**Branch:** audit/opus-4-7-review

All `except Exception:` handlers in `src/zeal/` were reviewed during Phase 1.
None are uncertain. All four instances are correctly broad, correctly logged, and
justified. No narrowing is recommended.

## Reviewed handlers

| Location | Pattern | Verdict |
|---|---|---|
| `ingestion/refresh.py:79` | `except Exception:` per-merchant catch | Correct: broad catch needed because any exception type can emerge from eBay API, DB, or pricing logic; `logger.exception(...)` logs full traceback; merchant is added to errored list; refresh continues |
| `ingestion/refresh.py:118` | `except Exception as exc:` outer run catch | Correct: marks refresh_run as `failed`; re-raises so caller sees the error |
| `ingestion/refresh.py:129` | `except Exception:` inner catch on DB update | Correct: prevents a DB failure from masking the original outer exception; `logger.exception(...)` logs it; outer `raise` still propagates |
| `web/routes/refresh.py:82` | `except Exception:` background task wrapper | Correct: top-level catch in a FastAPI background task (exceptions would otherwise be silently dropped); `logger.exception(...)` logs full traceback; `finally` closes DB connection |

## No action taken

No narrowing changes made. These handlers are at the correct level of
specificity for the operations they protect. Narrowing to specific exception
types (e.g., `httpx.HTTPError`) would miss unexpected exception types from DB
writes, pricing engine calls, and other code paths that also run inside the same
try block.
