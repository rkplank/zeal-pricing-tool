"""
Golden test: engine output must match every spreadsheet record in the baseline
fixture to within ±0.001.

Regenerate the fixture:
  uv run python scripts/extract_baseline.py \
      --emit-json tests/fixtures/spreadsheet_baseline.json

The test is skipped (not failed) when the fixture is absent so that fresh
clones without the workbook present don't break CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zeal.models.merchant import MerchantConfig
from zeal.models.pricing import GlobalConstants
from zeal.pricing.engine import compute_prices

_FIXTURE = Path(__file__).parent / "fixtures" / "spreadsheet_baseline.json"

# Global constants extracted from InputsandMargins (source: baseline extraction report).
# These mirror the spreadsheet's B2:B10 values exactly.  If the workbook changes,
# re-run extract_baseline.py and update these to match.
_CONSTANTS = GlobalConstants(
    ebay_sale_costs=0.13,
    paypal_sell_costs=0.03,
    ebay_postage_costs=0.01,
    online_store_postage_costs=0.03,
    online_sell_bonus_competitive=0.065,
    online_sell_bonus_zen_nocomp=0.085,
    in_store_bad_debt=0.048,
    in_mail_bad_debt=0.02,
    online_bad_debt=0.0,
)


def _load_records() -> list[dict]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "baseline_record" not in metafunc.fixturenames:
        return
    if not _FIXTURE.exists():
        metafunc.parametrize("baseline_record", [], ids=[])
        return
    records = _load_records()
    metafunc.parametrize(
        "baseline_record",
        records,
        ids=[r["merchant_id"] for r in records],
    )


_SKIP_REASON = "baseline fixture not present; run extract_baseline.py --emit-json"


@pytest.mark.skipif(not _FIXTURE.exists(), reason=_SKIP_REASON)
def test_engine_matches_spreadsheet_baseline(baseline_record: dict) -> None:
    cfg = MerchantConfig(**baseline_record["config"])
    ebay_pct: float | None = baseline_record["ebay_sell_input"]

    result = compute_prices(ebay_pct, "high", cfg, _CONSTANTS)

    expected: dict = baseline_record["expected"]
    sentinels: dict = baseline_record.get("expected_sentinels", {})

    _assert_channel("online_sell", expected["online_sell"], result.online_sell, sentinels)
    _assert_channel("in_mail_buy", expected["in_mail_buy"], result.in_mail_buy, sentinels)
    _assert_channel("in_store_buy", expected["in_store_buy"], result.in_store_buy, sentinels)
    _assert_channel("electronic_buy", expected["electronic_buy"], result.electronic_buy, sentinels)


def _assert_channel(
    name: str,
    expected_val: float | None,
    engine_val: object,
    sentinels: dict[str, str],
) -> None:
    if name in sentinels:
        # Spreadsheet had a sentinel (e.g. "No").  Engine should return None or "No".
        assert engine_val is None or engine_val == sentinels[name], (
            f"{name}: expected sentinel {sentinels[name]!r}, got {engine_val!r}"
        )
        return
    assert expected_val is not None, f"{name}: expected numeric but got None (check fixture)"
    assert isinstance(engine_val, (int, float)), (
        f"{name}: expected {expected_val:.4f}, engine returned {engine_val!r}"
    )
    diff = abs(float(engine_val) - expected_val)
    assert diff <= 0.001, (
        f"{name}: |engine {float(engine_val):.4f}"
        f" - spreadsheet {expected_val:.4f}| = {diff:.4f} > 0.001"
    )
