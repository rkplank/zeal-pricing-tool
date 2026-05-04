"""
Sanity tests for scripts/spreadsheet_parser.py.

These tests do NOT validate merchant values against the workbook (that is
extract_baseline.py's job).  They catch parser regressions without needing
the workbook present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ is not a package — add it to sys.path so we can import directly
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from spreadsheet_parser import (
    classify_row,
    extract_formula_refs,
    parse_workbook,
    slugify,
)

_DEFAULT_WORKBOOK = Path(
    r"C:\Users\kandt\OneDrive - Umich\Zeal Cards\Pricing\GiftCardPricingData_2025.xlsx"
)

# ---------------------------------------------------------------------------
# 1. Slug generation
# ---------------------------------------------------------------------------

_SLUG_CASES = [
    # General rule
    ("Mastercard", "mastercard"),
    ("Home Depot", "home_depot"),
    ("Amazon", "amazon"),
    ("TJ Maxx", "tj_maxx"),
    ("Bath & Body Works", "bath_body_works"),
    # Apostrophe → underscore → collapsed/stripped
    ("McDonald's", "mcdonald_s"),
    # Hard-coded aliases (recon §7.3)
    ("Home Depot Merch Credit (No ID)", "home_depot_merch_credit_no_id"),
    ("Home Depot Merch Credit (Tied to ID)", "home_depot_merch_credit_with_id"),
    ("Home Depot eStore Credit", "home_depot_estore_credit"),
    ("Menards Rebate", "menards_rebate"),
    ("Lowe's Merch Credit (No ID)", "lowes_merch_credit_no_id"),
    ("Ikea Merch Credit", "ikea_merch_credit"),
    ("Target Merch Credit", "target_merch_credit"),
    ("TJ Maxx / Homegoods / Marshalls Merch Credit", "tjm_homegoods_marshalls_merch_credit"),
]


@pytest.mark.parametrize("display_name,expected_slug", _SLUG_CASES)
def test_slugify(display_name: str, expected_slug: str) -> None:
    assert slugify(display_name) == expected_slug


# ---------------------------------------------------------------------------
# 2. Row classification
# ---------------------------------------------------------------------------

_CLASSIFY_CASES = [
    # (name_val, b_val, f_val, f_formula, expected_classification)
    # normal: F is a formula (not AVERAGE) and it computed a valid number
    ("Mastercard", 1.05, 1.005, "=B3-InputsandMargins!$B$23", "normal"),
    ("Home Depot", 0.92, 0.875, "=B11-InputsandMargins!$B$23", "normal"),
    # no_ebay_data_local (Pattern A): F is a literal number — f_formula is numeric, not a str
    ("Andiamo", "N/A", 0.65, 0.65, "no_ebay_data_local"),
    ("Plum Market", "N/A", 0.75, 0.75, "no_ebay_data_local"),
    # Biggby Coffee (row 253): B is numeric but F is a literal — must be no_ebay_data_local
    # (old B-keyed rule mis-classified this as "normal")
    ("Biggby Coffee", 0.668, 0.75, 0.75, "no_ebay_data_local"),
    # bankrupt_broken: F is a formula but evaluates to #VALUE! (f_val=None)
    ("Avenue", "N/A", None, "=B280-InputsandMargins!$B$23", "bankrupt_broken"),
    ("Bebe", "No Data", None, "=B281-InputsandMargins!$B$23", "bankrupt_broken"),
    # section_divider: name-keyed dividers
    ("PHYSICAL ONLY", None, None, None, "section_divider"),
    ("Bankrupt", None, None, None, "section_divider"),
    ("Merchant", None, None, None, "section_divider"),
    # section_divider: AVERAGE formula in F — operator-inserted aggregate rows
    ("BREAD AND BUTTER", None, 0.91, "=AVERAGE(F3:F18)", "section_divider"),
    ("TOP CARDS", None, 0.88, "=AVERAGE(F21:F59)", "section_divider"),
    # skip_blank
    (None, None, None, None, "skip_blank"),
    ("", None, None, None, "skip_blank"),
    ("   ", None, None, None, "skip_blank"),
]


@pytest.mark.parametrize("name_val,b_val,f_val,f_formula,expected", _CLASSIFY_CASES)
def test_classify_row(
    name_val: object, b_val: object, f_val: object, f_formula: object, expected: str
) -> None:
    assert classify_row(name_val, b_val, f_val, f_formula) == expected


# ---------------------------------------------------------------------------
# 3. Formula reference parsing
# ---------------------------------------------------------------------------

_FORMULA_REF_CASES = [
    # Mastercard row 3 F formula
    ("=B3-InputsandMargins!$B$23", ["B23"]),
    # Mastercard C formula (in_mail_buy)
    (
        "=F3-InputsandMargins!$B$12-InputsandMargins!$B$3-InputsandMargins!$B$9-InputsandMargins!$B$5",
        ["B12", "B3", "B9", "B5"],
    ),
    # Mastercard E formula (in_store_buy)
    (
        "=F3-InputsandMargins!$B$11-InputsandMargins!$B$3-InputsandMargins!$B$5-InputsandMargins!$B$8",
        ["B11", "B3", "B5", "B8"],
    ),
    # D formula (electronic_buy)
    ("=C3-InputsandMargins!$B$19", ["B19"]),
    # Zen differential
    ("=B100-InputsandMargins!$B$24", ["B24"]),
    # NC e-bonus special
    ("=C250-InputsandMargins!$B$21", ["B21"]),
    # Hardcoded cell (not a formula)
    (0.65, []),
    # Literal "No"
    ("No", []),
    # Non-string
    (None, []),
]


@pytest.mark.parametrize("formula,expected_refs", _FORMULA_REF_CASES)
def test_extract_formula_refs(formula: object, expected_refs: list[str]) -> None:
    assert extract_formula_refs(formula) == expected_refs


# ---------------------------------------------------------------------------
# 4. End-to-end smoke test (skipped if workbook absent)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _DEFAULT_WORKBOOK.exists(),
    reason="workbook not present at default path",
)
def test_parse_workbook_smoke() -> None:
    try:
        rows = parse_workbook(_DEFAULT_WORKBOOK)
    except PermissionError as exc:
        pytest.skip(f"workbook exists but is not readable: {exc}")

    assert len(rows) >= 200, f"Expected >= 200 rows, got {len(rows)}"

    classifications = {r.classification for r in rows}
    assert "normal" in classifications
    assert "no_ebay_data_local" in classifications
    assert "bankrupt_broken" in classifications
    assert "section_divider" in classifications

    merchant_rows = [r for r in rows if r.classification in ("normal", "no_ebay_data_local")]
    assert len(merchant_rows) >= 100, "Too few merchant rows"

    # All merchant rows should have a config and spreadsheet_outputs
    for r in merchant_rows:
        assert r.config is not None, f"Row {r.row_number} ({r.display_name}) missing config"
        assert r.spreadsheet_outputs is not None, f"Row {r.row_number} missing spreadsheet_outputs"
        assert r.merchant_id is not None
