import json
from pathlib import Path

from fastapi.testclient import TestClient

from zeal.db.connection import apply_schema, get_connection
from zeal.db.repositories import RecommendationSnapshot
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data
from zeal.ingestion.ebay_client import SyntheticEbayClient
from zeal.web.app import create_app
from zeal.web.routes.merchant import build_price_history_chart


def _seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "zeal.db"
    conn = get_connection(db_path)
    apply_schema(conn)
    seed_demo_data(conn, BASELINE_FIXTURE)
    conn.close()
    return db_path


def _config_payload(db_path: Path, merchant_id: str) -> dict[str, str]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM merchants WHERE merchant_id = ?",
            (merchant_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    payload = {
        "display_name": str(row["display_name"]),
        "tier": str(row["tier"]),
        "in_store_margin": _pct(row["in_store_margin"]),
        "in_mail_margin": _pct(row["in_mail_margin"]),
        "e_bonus": _pct(row["e_bonus"]),
        "ebay_differential": _pct(row["ebay_differential"]),
        "online_sell_override": _pct(row["online_sell_override"]),
        "electronic_buy_override": _pct(row["electronic_buy_override"]),
        "inclusion_regex": str(row["inclusion_regex"]),
        "exclusion_regex": str(row["exclusion_regex"] or ""),
        "notes": str(row["notes"] or ""),
        "reason": "test change",
    }
    for field in (
        "in_store_eligible",
        "in_mail_eligible",
        "electronic_eligible",
        "merch_credit_variant",
        "is_active",
    ):
        if row[field]:
            payload[field] = "1"
    return payload


def _pct(value: object) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}"


def _insert_recommendation_copy(
    db_path: Path,
    merchant_id: str,
    *,
    computed_at: str,
    **overrides: object,
) -> None:
    conn = get_connection(db_path)
    try:
        latest = conn.execute(
            """
            SELECT *
            FROM price_recommendations
            WHERE merchant_id = ?
            ORDER BY computed_at DESC, id DESC
            LIMIT 1
            """,
            (merchant_id,),
        ).fetchone()
        assert latest is not None
        cursor = conn.execute(
            """
            INSERT INTO refresh_runs (status, started_at, completed_at, processed, total)
            VALUES ('completed', ?, ?, 1, 1)
            """,
            (computed_at, computed_at),
        )
        values = {
            "online_sell": latest["online_sell"],
            "in_mail_buy": latest["in_mail_buy"],
            "in_store_buy": latest["in_store_buy"],
            "electronic_buy": latest["electronic_buy"],
            "ebay_sell_pct": latest["ebay_sell_pct"],
            "ebay_confidence": latest["ebay_confidence"],
            "no_data": latest["no_data"],
            "formula_breakdown_json": latest["formula_breakdown_json"],
            "config_snapshot_json": latest["config_snapshot_json"],
        }
        values.update(overrides)
        conn.execute(
            """
            INSERT INTO price_recommendations (
                merchant_id,
                refresh_run_id,
                online_sell,
                in_mail_buy,
                in_store_buy,
                electronic_buy,
                ebay_sell_pct,
                ebay_confidence,
                no_data,
                formula_breakdown_json,
                config_snapshot_json,
                computed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merchant_id,
                cursor.lastrowid,
                values["online_sell"],
                values["in_mail_buy"],
                values["in_store_buy"],
                values["electronic_buy"],
                values["ebay_sell_pct"],
                values["ebay_confidence"],
                values["no_data"],
                values["formula_breakdown_json"],
                values["config_snapshot_json"],
                computed_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _snapshot(
    computed_at: str,
    *,
    online_sell: float | None = None,
    in_mail_buy: float | None = None,
    ebay_sell_pct: float | None = None,
) -> RecommendationSnapshot:
    return RecommendationSnapshot(
        id=1,
        merchant_id="test",
        refresh_run_id=1,
        online_sell=online_sell,
        in_mail_buy=in_mail_buy,
        in_store_buy=None,
        electronic_buy=None,
        ebay_sell_pct=ebay_sell_pct,
        ebay_confidence="none",
        no_data=False,
        formula_breakdown={},
        config_snapshot={},
        computed_at=computed_at,
    )


def test_pricing_list_route_returns_200(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Pricing List" in response.text
    assert "Home Depot" in response.text
    assert "recommendations from saved tool outputs" in response.text
    assert "Mode: Synthetic" in response.text
    assert "Synthetic baseline mode — live eBay sold listings are not connected yet." in (
        response.text
    )
    assert "Awaiting production Marketplace Insights access" in response.text
    assert "do not mean live market prices are current" in response.text
    assert "Synthetic baseline" in response.text
    assert "row-synthetic" in response.text
    assert "numeric-cell" in response.text
    assert "row-config-override" in response.text
    assert "sticky-col" in response.text
    assert "badge-confidence" in response.text
    assert "recommendation-cell" in response.text
    assert "Delta columns populate after two or more refreshes." in response.text
    assert "last completed refresh" in response.text
    assert "with live eBay observations" in response.text


def test_merchant_detail_route_returns_200(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/home_depot")

    assert response.status_code == 200
    assert "Why this recommendation?" in response.text
    assert "Formula Breakdown" in response.text
    assert "No CardCash data yet" in response.text
    assert "Mode: Synthetic" in response.text
    assert "Synthetic baseline mode — live eBay sold listings are not connected yet." in (
        response.text
    )
    assert "Awaiting production Marketplace Insights access" in response.text
    assert "Synthetic baseline" in response.text
    assert "Why this recommendation?" in response.text
    expected_summary = (
        "Seeded spreadsheet-baseline values are displayed while production "
        "Marketplace Insights access is blocked."
    )
    assert expected_summary in response.text
    assert "Inputs, costs, and margins used for this channel." in response.text
    assert "Synthetic baseline mode has no live sold listings" in response.text
    assert "Reference-only in v1. Competitor data is not used in recommendations." in (
        response.text
    )
    assert "Edit config" in response.text
    assert "Price History" in response.text
    assert (
        "Recommendation history from saved tool outputs. This does not represent prices "
        "actually published or used outside the tool."
    ) in response.text


def test_price_history_chart_renders_with_two_recommendations(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    _insert_recommendation_copy(
        db_path,
        "home_depot",
        computed_at="2026-01-01T00:00:00Z",
        online_sell=0.86,
        in_mail_buy=0.71,
        ebay_sell_pct=0.91,
    )
    app = create_app(db_path)
    client = TestClient(app)

    response = client.get("/merchant/home_depot")

    assert response.status_code == 200
    assert "Recommendation history chart" in response.text
    assert "<polyline" in response.text
    assert "Online sell" in response.text
    assert "In-mail buy" in response.text
    assert "eBay sell" in response.text


def test_price_history_empty_state_with_single_recommendation(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/home_depot")

    assert response.status_code == 200
    assert "History chart will appear after two recommendations exist." in response.text
    assert "Recommendation History" in response.text


def test_price_history_chart_handles_unexpected_timestamps() -> None:
    chart = build_price_history_chart(
        [
            _snapshot("", online_sell=0.82),
            _snapshot("not-a-normal-timestamp", online_sell=0.84),
        ]
    )

    assert chart.has_chart is True
    assert chart.first_label == "not-a-normal-timestamp"
    assert chart.last_label == "Unknown date"


def test_price_history_chart_empty_state_when_no_channel_has_two_points() -> None:
    chart = build_price_history_chart(
        [
            _snapshot("2026-01-02T00:00:00Z", online_sell=0.82),
            _snapshot("2026-01-01T00:00:00Z", ebay_sell_pct=0.91),
        ]
    )

    assert chart.has_chart is False
    assert chart.empty_message == "History chart will appear after two usable points exist."


def test_price_history_chart_handles_missing_values(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    conn = get_connection(db_path)
    try:
        config_snapshot = conn.execute(
            """
            SELECT config_snapshot_json
            FROM price_recommendations
            WHERE merchant_id = ?
            ORDER BY computed_at DESC, id DESC
            LIMIT 1
            """,
            ("home_depot_estore_credit",),
        ).fetchone()
    finally:
        conn.close()
    assert config_snapshot is not None
    snapshot = json.loads(str(config_snapshot["config_snapshot_json"]))
    snapshot["in_mail_eligible"] = False
    _insert_recommendation_copy(
        db_path,
        "home_depot_estore_credit",
        computed_at="2026-01-01T00:00:00Z",
        in_mail_buy=None,
        ebay_sell_pct=None,
        config_snapshot_json=json.dumps(snapshot),
    )
    app = create_app(db_path)
    client = TestClient(app)

    response = client.get("/merchant/home_depot_estore_credit")

    assert response.status_code == 200
    assert "Recommendation history chart" in response.text
    assert "Not offered" in response.text


def test_price_history_copy_stays_recommendation_scoped(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/home_depot")

    assert response.status_code == 200
    assert "Recommendation history from saved tool outputs." in response.text
    assert "accepted price" not in response.text
    assert "operator action" not in response.text


def test_merchant_config_page_loads_with_percent_values(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/home_depot/config")

    assert response.status_code == 200
    assert "Edit config" in response.text
    assert 'name="in_store_margin" value="25.0"' in response.text
    assert 'name="in_mail_margin" value="7.0"' in response.text
    assert 'name="ebay_differential" value="4.5"' in response.text
    assert "Config changes apply to future recommendations" in response.text
    assert "Enter percentages as 85.0 for 85.0%. Values are stored internally as 0.850." in (
        response.text
    )
    assert "Leave blank to use the formula." in response.text
    assert "ebay_weight" not in response.text


def test_merchant_config_save_updates_margin_and_history(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    app = create_app(db_path)
    client = TestClient(app)
    payload = _config_payload(db_path, "home_depot")
    payload["in_mail_margin"] = "8.5%"
    payload["reason"] = "adjust mail margin"

    response = client.post("/merchant/home_depot/config", data=payload, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/merchant/home_depot?saved=1"
    conn = get_connection(db_path)
    try:
        merchant = conn.execute(
            "SELECT in_mail_margin FROM merchants WHERE merchant_id = ?",
            ("home_depot",),
        ).fetchone()
        history = conn.execute(
            """
            SELECT field_name, old_value, new_value, reason
            FROM merchant_config_history
            WHERE merchant_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("home_depot",),
        ).fetchone()
    finally:
        conn.close()
    assert merchant is not None
    assert merchant["in_mail_margin"] == 0.085
    assert history is not None
    assert history["field_name"] == "in_mail_margin"
    assert history["old_value"] == "0.07"
    assert history["new_value"] == "0.085"
    assert history["reason"] == "adjust mail margin"


def test_merchant_config_blank_nullable_override_stores_null(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    app = create_app(db_path)
    client = TestClient(app)
    payload = _config_payload(db_path, "andiamo")
    payload["online_sell_override"] = ""

    response = client.post("/merchant/andiamo/config", data=payload, follow_redirects=False)

    assert response.status_code == 303
    conn = get_connection(db_path)
    try:
        merchant = conn.execute(
            "SELECT online_sell_override FROM merchants WHERE merchant_id = ?",
            ("andiamo",),
        ).fetchone()
        history = conn.execute(
            """
            SELECT field_name, old_value, new_value
            FROM merchant_config_history
            WHERE merchant_id = ? AND field_name = 'online_sell_override'
            """,
            ("andiamo",),
        ).fetchone()
    finally:
        conn.close()
    assert merchant is not None
    assert merchant["online_sell_override"] is None
    assert history is not None
    assert history["old_value"] == "0.85"
    assert history["new_value"] is None


def test_merchant_config_invalid_percentage_is_rejected(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    app = create_app(db_path)
    client = TestClient(app)
    payload = _config_payload(db_path, "home_depot")
    payload["in_store_margin"] = "0.85"

    response = client.post("/merchant/home_depot/config", data=payload)

    assert response.status_code == 400
    assert "Enter human percentages like 85 or 85%, not fractions like 0.85." in response.text
    assert 'name="in_store_margin" value="0.85"' in response.text


def test_config_editor_does_not_introduce_operator_workflow_tables(tmp_path: Path) -> None:
    db_path = _seeded_db(tmp_path)
    conn = get_connection(db_path)
    try:
        table_names = {
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        conn.close()
    assert "published_prices" not in table_names
    assert "operator_actions" not in table_names


def test_merchant_detail_config_override_summary(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/home_depot_estore_credit")

    assert response.status_code == 200
    assert "Config override" in response.text
    assert "Configured merchant settings supply the electronic buy value for the formula." in (
        response.text
    )
    assert "Not offered" in response.text


def test_merchant_detail_online_config_override_summary(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/andiamo")

    assert response.status_code == 200
    assert "Config override" in response.text
    expected_summary = (
        "Configured merchant settings supply the online sell value instead of live eBay data."
    )
    assert expected_summary in response.text


def test_missing_merchant_returns_404(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/not_real")

    assert response.status_code == 404


def test_lifespan_synthetic_mode_creates_shared_client(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ZEAL_EBAY_MODE", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("EBAY_ENVIRONMENT", raising=False)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "synthetic")
    app = create_app(_seeded_db(tmp_path))

    with TestClient(app):
        ebay_client = app.state.ebay_client_factory()
        assert isinstance(ebay_client, SyntheticEbayClient)
        assert app.state.ebay_client_factory() is ebay_client

    assert app.state.http_client.is_closed is True


def test_live_mode_shows_live_badge_without_synthetic_banner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ZEAL_EBAY_MODE", "live")
    monkeypatch.setenv("EBAY_CLIENT_ID", "client-id")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "client-secret")
    monkeypatch.delenv("EBAY_ENVIRONMENT", raising=False)
    app = create_app(_seeded_db(tmp_path))

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Mode: Live eBay" in response.text
    assert "Synthetic baseline" in response.text
    assert "Synthetic baseline mode — live eBay sold listings are not connected yet." not in (
        response.text
    )


def test_lifespan_preserves_existing_ebay_client_factory_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    sentinel = SyntheticEbayClient()
    monkeypatch.delenv("ZEAL_EBAY_MODE", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("EBAY_ENVIRONMENT", raising=False)
    app = create_app(_seeded_db(tmp_path))
    app.state.ebay_client_factory = lambda: sentinel

    with TestClient(app):
        assert app.state.ebay_client_factory() is sentinel
