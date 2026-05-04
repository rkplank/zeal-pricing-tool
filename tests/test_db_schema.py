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
    "competitor_sources",
    "competitor_observations",
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


def test_merchant_v1_columns_and_constraints() -> None:
    conn = _make_conn()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(merchants)")}
    assert {"ebay_weight", "risk_status", "risk_note"} <= columns

    conn.execute(_INSERT_MERCHANT, _VALID_MERCHANT)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO merchants (
                merchant_id, display_name, tier,
                in_store_margin, in_mail_margin, ebay_differential,
                in_store_eligible, in_mail_eligible, electronic_eligible,
                merch_credit_variant, inclusion_regex, ebay_weight
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("bad_weight", "Bad", "C", 0.25, 0.03, 0.045, 1, 1, 0, 0, "bad", 1.5),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO merchants (
                merchant_id, display_name, tier,
                in_store_margin, in_mail_margin, ebay_differential,
                in_store_eligible, in_mail_eligible, electronic_eligible,
                merch_credit_variant, inclusion_regex, risk_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("bad_risk", "Bad", "C", 0.25, 0.03, 0.045, 1, 1, 0, 0, "bad", "invalid"),
        )


def test_ebay_validity_columns_and_constraints() -> None:
    conn = _make_conn()
    conn.execute(_INSERT_MERCHANT, _VALID_MERCHANT)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ebay_observations)")}
    assert {"validity_status", "exclusion_reason"} <= columns

    conn.execute(
        """
        INSERT INTO ebay_observations (
            merchant_id, listing_id, sold_at, face_value, sale_price, title, validity_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("t1", "listing1", "2026-05-04", 100.0, 90.0, "Test", "valid"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO ebay_observations (
                merchant_id, listing_id, sold_at, face_value, sale_price, title, validity_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("t1", "listing2", "2026-05-04", 100.0, 90.0, "Test", "invalid"),
        )


def test_competitor_table_constraints() -> None:
    conn = _make_conn()
    conn.execute(_INSERT_MERCHANT, _VALID_MERCHANT)
    conn.execute(
        """
        INSERT INTO competitor_sources (
            source_name, collection_method, refresh_interval_days
        ) VALUES (?, ?, ?)
        """,
        ("cardcash", "scraper", 7),
    )
    conn.execute(
        """
        INSERT INTO competitor_observations (
            merchant_id, source_name, channel, price_pct, availability, confidence, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("t1", "cardcash", "buy_mail", 0.74, "available", "high", "2026-05-04T00:00:00Z"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO competitor_observations (
                merchant_id, source_name, channel, price_pct, availability, confidence, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("t1", "cardcash", "invalid", 0.74, "available", "high", "2026-05-04T00:00:00Z"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO competitor_observations (
                merchant_id, source_name, channel, price_pct, availability, confidence, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("t1", "cardcash", "buy_mail", 0.74, "maybe", "high", "2026-05-04T00:00:00Z"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO competitor_observations (
                merchant_id, source_name, channel, price_pct, availability, confidence, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("t1", "cardcash", "buy_mail", 0.74, "available", "bad", "2026-05-04T00:00:00Z"),
        )
