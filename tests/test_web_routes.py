from pathlib import Path

from fastapi.testclient import TestClient

from zeal.db.connection import apply_schema, get_connection
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data
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


def test_merchant_detail_route_returns_200(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/home_depot")

    assert response.status_code == 200
    assert "Formula Breakdown" in response.text
    assert "No CardCash data yet" in response.text


def test_missing_merchant_returns_404(tmp_path: Path) -> None:
    app = create_app(_seeded_db(tmp_path))
    client = TestClient(app)

    response = client.get("/merchant/not_real")

    assert response.status_code == 404
