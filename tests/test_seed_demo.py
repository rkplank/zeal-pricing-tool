import sqlite3
from pathlib import Path

from zeal.db.connection import apply_schema
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return conn


def test_seed_demo_creates_refresh_run_and_recommendations() -> None:
    conn = _conn()
    run_id = seed_demo_data(conn, BASELINE_FIXTURE)

    run_count = conn.execute("SELECT COUNT(*) FROM refresh_runs").fetchone()[0]
    rec_count = conn.execute("SELECT COUNT(*) FROM price_recommendations").fetchone()[0]
    merchant_count = conn.execute("SELECT COUNT(*) FROM merchants").fetchone()[0]

    assert run_id > 0
    assert run_count == 1
    assert rec_count == merchant_count
    assert rec_count > 0


def test_seed_demo_accepts_explicit_fixture_path(tmp_path: Path) -> None:
    conn = _conn()
    fixture_copy = tmp_path / "baseline.json"
    fixture_copy.write_text(BASELINE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    seed_demo_data(conn, fixture_copy)

    assert conn.execute("SELECT COUNT(*) FROM global_constants").fetchone()[0] > 0


def test_seed_demo_online_bad_debt_matches_spec_baseline() -> None:
    conn = _conn()
    seed_demo_data(conn, BASELINE_FIXTURE)

    value = conn.execute(
        "SELECT value FROM global_constants WHERE key = 'online_bad_debt'"
    ).fetchone()[0]

    assert value == 0.05
