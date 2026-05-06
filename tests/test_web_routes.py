from pathlib import Path

from fastapi.testclient import TestClient

from zeal.db.connection import apply_schema, get_connection
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data
from zeal.ingestion.ebay_client import SyntheticEbayClient
from zeal.web.app import create_app


def _seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "zeal.db"
    conn = get_connection(db_path)
    apply_schema(conn)
    seed_demo_data(conn, BASELINE_FIXTURE)
    conn.close()
    return db_path


def test_pricing_list_route_returns_200(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Pricing List" in response.text
    assert "Home Depot" in response.text
    assert "Mode: Synthetic" in response.text
    assert "Viewing seeded baseline recommendations. Live eBay data is not connected yet." in (
        response.text
    )
    assert "Delta columns populate after two or more refreshes." in response.text


def test_merchant_detail_route_returns_200(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/home_depot")

    assert response.status_code == 200
    assert "Formula Breakdown" in response.text
    assert "No CardCash data yet" in response.text
    assert "Mode: Synthetic" in response.text
    assert (
        "No live eBay observations yet. Current recommendations are seeded from the "
        "spreadsheet baseline. Live observations will appear after a successful eBay refresh."
    ) in response.text


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
    assert "Viewing seeded baseline recommendations. Live eBay data is not connected yet." not in (
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
