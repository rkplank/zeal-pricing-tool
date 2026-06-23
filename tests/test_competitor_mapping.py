"""Tests for Phase 3 merchant-match tooling: normalization, apply path, lookup query.

All DB tests use an in-memory SQLite; no live network; no data/zeal.db.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from zeal.db.competitor_mapping import (
    MappingResult,
    apply_cardcash_mapping,
    normalize_merchant_name,
)
from zeal.db.connection import apply_schema
from zeal.db.repositories import (
    MerchantForRefresh,
    get_merchants_for_competitor_refresh,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return conn


def _add_merchant(
    conn: sqlite3.Connection,
    merchant_id: str,
    display_name: str,
    *,
    cardcash_id: int | None = None,
    is_active: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO merchants (
            merchant_id, display_name, tier,
            in_store_margin, in_mail_margin, ebay_differential,
            in_store_eligible, in_mail_eligible, electronic_eligible,
            merch_credit_variant, inclusion_regex, is_active
        ) VALUES (?, ?, 'T24', 0.05, 0.05, 0.02, 1, 1, 1, 0, '.*', ?)
        """,
        (merchant_id, display_name, is_active),
    )
    if cardcash_id is not None:
        conn.execute(
            "UPDATE merchants SET cardcash_id = ? WHERE merchant_id = ?",
            (cardcash_id, merchant_id),
        )
    conn.commit()


def _write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "mapping.csv"
    fields = [
        "zeal_merchant_id",
        "zeal_display_name",
        "proposed_cardcash_id",
        "cardcash_name",
        "score",
        "match_tier",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# normalize_merchant_name — unit tests (no DB)
# ---------------------------------------------------------------------------


def test_normalize_basic() -> None:
    assert normalize_merchant_name("Starbucks") == "starbucks"


def test_normalize_registered_trademark() -> None:
    assert normalize_merchant_name("Home Depot®") == "home depot"


def test_normalize_trademark_symbol() -> None:
    assert normalize_merchant_name("iTunes™") == "itunes"


def test_normalize_leading_the() -> None:
    assert normalize_merchant_name("The Home Depot") == "home depot"


def test_normalize_ampersand() -> None:
    assert normalize_merchant_name("Bed Bath & Beyond") == "bed bath beyond"


def test_normalize_apostrophe() -> None:
    assert normalize_merchant_name("McDonald's") == "mcdonald s"


def test_normalize_legal_suffix_inc() -> None:
    assert normalize_merchant_name("Apple Inc.") == "apple"


def test_normalize_legal_suffix_llc() -> None:
    assert normalize_merchant_name("Some Brand LLC") == "some brand"


def test_normalize_legal_suffix_corp() -> None:
    assert normalize_merchant_name("Big Corp Corp") == "big"


def test_normalize_multiple_suffixes() -> None:
    assert normalize_merchant_name("Foo LLC Corp") == "foo"


def test_normalize_dash_in_name() -> None:
    assert normalize_merchant_name("7-Eleven") == "7 eleven"


def test_normalize_collapse_whitespace() -> None:
    assert normalize_merchant_name("  Gap   Inc  ") == "gap"


def test_normalize_already_clean() -> None:
    assert normalize_merchant_name("target") == "target"


def test_normalize_unicode_accented() -> None:
    # é decomposes to e + combining accent; ASCII encode drops the accent.
    assert normalize_merchant_name("Café") == "cafe"


# ---------------------------------------------------------------------------
# apply_cardcash_mapping — unit tests (in-memory DB + tmp CSV)
# ---------------------------------------------------------------------------


def test_apply_updates_merchant(tmp_path: Path) -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot")
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "zeal_merchant_id": "home_depot",
                "proposed_cardcash_id": "27",
                "zeal_display_name": "Home Depot",
                "cardcash_name": "Home Depot®",
                "score": "1.0000",
                "match_tier": "exact",
            }
        ],
    )

    result = apply_cardcash_mapping(conn, csv_path)

    assert result.updated == 1
    assert result.skipped == 0
    assert result.conflicted == 0
    row = conn.execute(
        "SELECT cardcash_id FROM merchants WHERE merchant_id = 'home_depot'"
    ).fetchone()
    assert row["cardcash_id"] == 27


def test_apply_skips_empty_proposed_id(tmp_path: Path) -> None:
    conn = _make_db()
    _add_merchant(conn, "unknown_brand", "Unknown Brand")
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "zeal_merchant_id": "unknown_brand",
                "proposed_cardcash_id": "",
                "zeal_display_name": "Unknown Brand",
                "cardcash_name": "",
                "score": "",
                "match_tier": "none",
            }
        ],
    )

    result = apply_cardcash_mapping(conn, csv_path)

    assert result.updated == 0
    assert result.skipped == 1
    row = conn.execute(
        "SELECT cardcash_id FROM merchants WHERE merchant_id = 'unknown_brand'"
    ).fetchone()
    assert row["cardcash_id"] is None


def test_apply_skips_merchant_not_in_db(tmp_path: Path) -> None:
    conn = _make_db()
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "zeal_merchant_id": "ghost_merchant",
                "proposed_cardcash_id": "999",
                "zeal_display_name": "Ghost",
                "cardcash_name": "Ghost",
                "score": "0.9500",
                "match_tier": "high",
            }
        ],
    )

    result = apply_cardcash_mapping(conn, csv_path)

    assert result.updated == 0
    assert result.skipped == 1


def test_apply_refuses_overwrite_without_force(tmp_path: Path) -> None:
    conn = _make_db()
    _add_merchant(conn, "starbucks", "Starbucks", cardcash_id=54)
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "zeal_merchant_id": "starbucks",
                "proposed_cardcash_id": "999",
                "zeal_display_name": "Starbucks",
                "cardcash_name": "Starbucks",
                "score": "1.0000",
                "match_tier": "exact",
            }
        ],
    )

    result = apply_cardcash_mapping(conn, csv_path)

    assert result.updated == 0
    assert result.conflicted == 1
    assert result.conflict_details == [("starbucks", 54, 999)]
    row = conn.execute(
        "SELECT cardcash_id FROM merchants WHERE merchant_id = 'starbucks'"
    ).fetchone()
    assert row["cardcash_id"] == 54  # unchanged


def test_apply_force_flag_allows_overwrite(tmp_path: Path) -> None:
    conn = _make_db()
    _add_merchant(conn, "starbucks", "Starbucks", cardcash_id=54)
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "zeal_merchant_id": "starbucks",
                "proposed_cardcash_id": "55",
                "zeal_display_name": "Starbucks",
                "cardcash_name": "Starbucks Coffee",
                "score": "0.9300",
                "match_tier": "high",
            }
        ],
    )

    result = apply_cardcash_mapping(conn, csv_path, force=True)

    assert result.updated == 1
    assert result.conflicted == 0
    row = conn.execute(
        "SELECT cardcash_id FROM merchants WHERE merchant_id = 'starbucks'"
    ).fetchone()
    assert row["cardcash_id"] == 55


def test_apply_commits_non_conflicting_rows(tmp_path: Path) -> None:
    """Non-conflicting rows are committed even when a conflict is present in the same CSV."""
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot")
    _add_merchant(conn, "starbucks", "Starbucks", cardcash_id=54)
    csv_path = _write_csv(
        tmp_path,
        [
            {
                "zeal_merchant_id": "home_depot",
                "proposed_cardcash_id": "27",
                "zeal_display_name": "Home Depot",
                "cardcash_name": "Home Depot®",
                "score": "1.0000",
                "match_tier": "exact",
            },
            {
                "zeal_merchant_id": "starbucks",
                "proposed_cardcash_id": "999",
                "zeal_display_name": "Starbucks",
                "cardcash_name": "Starbucks",
                "score": "1.0000",
                "match_tier": "exact",
            },
        ],
    )

    result = apply_cardcash_mapping(conn, csv_path)

    assert result.updated == 1
    assert result.conflicted == 1
    assert (
        conn.execute(
            "SELECT cardcash_id FROM merchants WHERE merchant_id = 'home_depot'"
        ).fetchone()["cardcash_id"]
        == 27
    )
    assert (
        conn.execute(
            "SELECT cardcash_id FROM merchants WHERE merchant_id = 'starbucks'"
        ).fetchone()["cardcash_id"]
        == 54
    )  # conflict, unchanged


def test_apply_result_type() -> None:
    """MappingResult fields are present and typed correctly."""
    result = MappingResult(updated=2, skipped=1, conflicted=0)
    assert result.updated == 2
    assert result.conflict_details == []


# ---------------------------------------------------------------------------
# get_merchants_for_competitor_refresh — unit tests (in-memory DB)
# ---------------------------------------------------------------------------


def test_lookup_returns_only_mapped_merchants() -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot", cardcash_id=27)
    _add_merchant(conn, "starbucks", "Starbucks")  # no cardcash_id

    result = get_merchants_for_competitor_refresh(conn)

    assert len(result) == 1
    assert result[0].merchant_id == "home_depot"
    assert result[0].cardcash_id == 27


def test_lookup_excludes_inactive_merchants() -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot", cardcash_id=27)
    _add_merchant(conn, "starbucks", "Starbucks", cardcash_id=54, is_active=0)

    result = get_merchants_for_competitor_refresh(conn)

    assert len(result) == 1
    assert result[0].merchant_id == "home_depot"


def test_lookup_ordered_by_display_name() -> None:
    conn = _make_db()
    _add_merchant(conn, "target", "Target", cardcash_id=100)
    _add_merchant(conn, "amazon", "Amazon", cardcash_id=101)
    _add_merchant(conn, "walmart", "Walmart", cardcash_id=102)

    result = get_merchants_for_competitor_refresh(conn)

    assert [r.display_name for r in result] == ["Amazon", "Target", "Walmart"]


def test_lookup_returns_empty_when_none_mapped() -> None:
    conn = _make_db()
    _add_merchant(conn, "starbucks", "Starbucks")

    result = get_merchants_for_competitor_refresh(conn)

    assert result == []


def test_lookup_return_type() -> None:
    conn = _make_db()
    _add_merchant(conn, "home_depot", "Home Depot", cardcash_id=27)

    result = get_merchants_for_competitor_refresh(conn)

    assert isinstance(result[0], MerchantForRefresh)
    assert isinstance(result[0].cardcash_id, int)


# ---------------------------------------------------------------------------
# Smoke-test: parse_catalog works on the real fixture (import only)
# ---------------------------------------------------------------------------


def test_parse_catalog_smoke() -> None:
    """Confirm the real fixture can be parsed — guards the script's data source."""
    from zeal.ingestion.competitor.cardcash import CardCashClient

    html = Path("tests/fixtures/cardcash/buy_catalog.html").read_text(encoding="utf-8")
    catalog = CardCashClient.parse_catalog(html)
    assert len(catalog) > 100
    assert 27 in catalog
    assert str(catalog[27]["name"]).startswith("Home Depot")
    assert "aliases" in catalog[27]
