import sqlite3

import pytest

from zeal.db.connection import apply_schema

EXPECTED_TABLES = {
    "merchants",
    "merchant_config_history",
    "global_constants",
    "global_constants_history",
    "ebay_observations",
    "ebay_summary",
    "price_recommendations",
    "published_prices",
    "operator_actions",
    "refresh_runs",
}

_VALID_MERCHANT = (
    "t1",     # merchant_id
    "Test",   # display_name
    "T24",    # tier
    0.25,     # in_store_margin
    0.03,     # in_mail_margin
    0.045,    # ebay_differential
    1,        # in_store_eligible
    1,        # in_mail_eligible
    0,        # electronic_eligible
    0,        # merch_credit_variant
    "test",   # inclusion_regex
)

_INSERT_MERCHANT = """
    INSERT INTO merchants (
        merchant_id, display_name, tier,
        in_store_margin, in_mail_margin, ebay_differential,
        in_store_eligible, in_mail_eligible, electronic_eligible,
        merch_credit_variant, inclusion_regex
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


def test_all_expected_tables_exist() -> None:
    conn = _make_conn()
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert EXPECTED_TABLES <= tables


def test_tier_check_constraint_rejects_invalid_value() -> None:
    conn = _make_conn()
    bad_row = ("t1", "Test", "INVALID", 0.25, 0.03, 0.045, 1, 1, 0, 0, "test")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_INSERT_MERCHANT, bad_row)


def test_tier_check_constraint_accepts_valid_values() -> None:
    conn = _make_conn()
    for i, tier in enumerate(("T24", "C", "Z", "NC")):
        row = (
            f"m{i}", "Test", tier,
            0.25, 0.03, 0.045, 1, 1, 0, 0, "test",
        )
        conn.execute(_INSERT_MERCHANT, row)
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM merchants").fetchone()[0]
    assert count == 4


def test_eligibility_check_constraint_rejects_invalid_value() -> None:
    conn = _make_conn()
    bad_row = ("t1", "Test", "T24", 0.25, 0.03, 0.045, 2, 1, 0, 0, "test")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_INSERT_MERCHANT, bad_row)


def test_schema_is_idempotent() -> None:
    conn = _make_conn()
    # Second application must not raise (CREATE TABLE IF NOT EXISTS).
    apply_schema(conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert EXPECTED_TABLES <= tables
