import sqlite3

import pytest

from zeal.db.connection import apply_schema
from zeal.db.repositories import (
    delta_from_prior,
    fetch_merchant_detail,
    fetch_pricing_list,
    fetch_recommendation_history,
    max_absolute_delta_over_window,
)
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return conn


def test_list_query_returns_merchants_with_latest_recommendations() -> None:
    conn = _conn()
    seed_demo_data(conn, BASELINE_FIXTURE)

    rows = fetch_pricing_list(conn)

    assert rows
    assert rows[0].latest is not None
    assert rows[0].latest.formula_breakdown


def test_delta_helpers_with_one_run_return_empty_delta() -> None:
    conn = _conn()
    seed_demo_data(conn, BASELINE_FIXTURE)
    history = fetch_recommendation_history(conn, "home_depot")

    assert delta_from_prior(history) == (None, None)
    assert max_absolute_delta_over_window(history, 5) == (None, None)


def test_delta_helpers_with_multiple_runs_return_largest_channel_movement() -> None:
    conn = _conn()
    seed_demo_data(conn, BASELINE_FIXTURE)
    run_id = conn.execute(
        """
        INSERT INTO refresh_runs (status, completed_at, processed, total)
        VALUES ('completed', datetime('now', '+1 minute'), 1, 1)
        RETURNING id
        """
    ).fetchone()[0]
    latest = fetch_recommendation_history(conn, "home_depot")[0]
    conn.execute(
        """
        INSERT INTO price_recommendations (
            merchant_id, refresh_run_id,
            online_sell, in_mail_buy, in_store_buy, electronic_buy,
            ebay_sell_pct, ebay_confidence, no_data,
            formula_breakdown_json, config_snapshot_json,
            computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '+1 minute'))
        """,
        (
            "home_depot",
            run_id,
            latest.online_sell + 0.01 if latest.online_sell is not None else None,
            latest.in_mail_buy + 0.03 if latest.in_mail_buy is not None else None,
            latest.in_store_buy,
            latest.electronic_buy,
            latest.ebay_sell_pct,
            latest.ebay_confidence,
            0,
            "{}",
            "{}",
        ),
    )
    conn.commit()

    history = fetch_recommendation_history(conn, "home_depot")

    delta, channel = delta_from_prior(history)
    assert delta == pytest.approx(0.03)
    assert channel == "in_mail_buy"
    max_delta, max_channel = max_absolute_delta_over_window(history, 5)
    assert max_delta == pytest.approx(0.03)
    assert max_channel == "in_mail_buy"


def test_detail_query_returns_latest_recommendation_and_history() -> None:
    conn = _conn()
    seed_demo_data(conn, BASELINE_FIXTURE)

    detail = fetch_merchant_detail(conn, "home_depot")

    assert detail is not None
    assert detail.latest is not None
    assert detail.history
    assert detail.recent_refreshes
