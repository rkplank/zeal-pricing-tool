from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from zeal import cli
from zeal.db.connection import apply_schema, get_connection
from zeal.db.seed import BASELINE_FIXTURE, seed_demo_data
from zeal.ingestion.ebay_errors import EbayAuthError
from zeal.models.ebay import EbaySoldListing


def _seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "zeal.db"
    conn = get_connection(db_path)
    apply_schema(conn)
    seed_demo_data(conn, BASELINE_FIXTURE)
    conn.close()
    return db_path


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    for name in (
        "ZEAL_EBAY_MODE",
        "EBAY_CLIENT_ID",
        "EBAY_CLIENT_SECRET",
        "EBAY_ENVIRONMENT",
        "ZEAL_DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_synthetic_mode_known_merchant_prints_sections(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    ) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "synthetic")
    monkeypatch.setenv("ZEAL_DB_PATH", str(_seeded_db(tmp_path)))
    monkeypatch.setattr(sys, "argv", ["zeal", "smoke-ebay", "--merchant", "home_depot"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    output = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert "Warning: ZEAL_EBAY_MODE=synthetic" in output
    assert "Merchant: Home Depot" in output
    assert "Inclusion regex:" in output
    assert "Raw listings returned:" in output
    assert "Valid listings:" in output
    assert "Exclusion reasons:" in output


def test_unknown_merchant_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    ) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "synthetic")
    monkeypatch.setenv("ZEAL_DB_PATH", str(_seeded_db(tmp_path)))
    monkeypatch.setattr(sys, "argv", ["zeal", "smoke-ebay", "--merchant", "not_real"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1
    assert "Merchant not found: not_real" in capsys.readouterr().out


def test_ebay_client_error_prints_clean_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class _FailingClient:
        async def sold_listings_for_merchant(
            self,
            *,
            merchant_id: str,
            inclusion_regex: str,
            exclusion_regex: str | None,
        ) -> Sequence[EbaySoldListing]:
            raise EbayAuthError("bad credentials")

    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "synthetic")
    monkeypatch.setenv("ZEAL_DB_PATH", str(_seeded_db(tmp_path)))
    monkeypatch.setattr(sys, "argv", ["zeal", "smoke-ebay", "--merchant", "home_depot"])
    monkeypatch.setattr(cli, "create_ebay_client", lambda **kwargs: _FailingClient())

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1
    assert "EbayAuthError: bad credentials" in capsys.readouterr().out


def test_limit_is_passed_to_live_client_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _EmptyClient:
        async def sold_listings_for_merchant(
            self,
            *,
            merchant_id: str,
            inclusion_regex: str,
            exclusion_regex: str | None,
        ) -> Sequence[EbaySoldListing]:
            return []

    seen: dict[str, int | None] = {}

    def _factory(**kwargs: object) -> _EmptyClient:
        seen["max_results_default"] = kwargs["max_results_default"]  # type: ignore[assignment]
        return _EmptyClient()

    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "live")
    monkeypatch.setenv("EBAY_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("ZEAL_DB_PATH", str(_seeded_db(tmp_path)))
    monkeypatch.setattr(
        sys,
        "argv",
        ["zeal", "smoke-ebay", "--merchant", "home_depot", "--limit", "7"],
    )
    monkeypatch.setattr(cli, "create_ebay_client", _factory)

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 0
    assert seen["max_results_default"] == 7


def test_invalid_scope_guidance_prints_clean_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class _FailingClient:
        async def sold_listings_for_merchant(
            self,
            *,
            merchant_id: str,
            inclusion_regex: str,
            exclusion_regex: str | None,
        ) -> Sequence[EbaySoldListing]:
            raise EbayAuthError(
                "The production keyset cannot mint the Marketplace Insights scope. "
                "Check the eBay Developer Portal under Production -> Client Credential "
                "Grant Type scopes. Do not run the first-five pilot or fall back to "
                "Browse API."
            )

    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "synthetic")
    monkeypatch.setenv("ZEAL_DB_PATH", str(_seeded_db(tmp_path)))
    monkeypatch.setattr(sys, "argv", ["zeal", "smoke-ebay", "--merchant", "home_depot"])
    monkeypatch.setattr(cli, "create_ebay_client", lambda **kwargs: _FailingClient())

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    output = capsys.readouterr().out
    assert excinfo.value.code == 1
    assert "EbayAuthError: The production keyset cannot mint" in output
    assert "Production -> Client Credential Grant Type scopes" in output
    assert "Do not run the first-five pilot or fall back to Browse API" in output
