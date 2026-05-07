from pathlib import Path

import pytest

from zeal.config import ZealConfig


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


def test_default_env_uses_synthetic_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)

    config = ZealConfig.from_env()

    assert config.ebay_mode == "synthetic"
    assert config.ebay_environment == "production"
    assert config.ebay_client_id is None
    assert config.ebay_client_secret is None


def test_live_mode_works_with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "live")
    monkeypatch.setenv("EBAY_CLIENT_ID", "client-id")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "client-secret")

    config = ZealConfig.from_env()

    assert config.ebay_mode == "live"
    assert config.ebay_client_id == "client-id"
    assert config.ebay_client_secret == "client-secret"


def test_live_mode_requires_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "live")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "client-secret")

    with pytest.raises(ValueError, match="EBAY_CLIENT_ID"):
        ZealConfig.from_env()


def test_live_mode_requires_client_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "live")
    monkeypatch.setenv("EBAY_CLIENT_ID", "client-id")

    with pytest.raises(ValueError, match="EBAY_CLIENT_SECRET"):
        ZealConfig.from_env()


def test_invalid_ebay_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ZEAL_EBAY_MODE", "browse")

    with pytest.raises(ValueError, match="ZEAL_EBAY_MODE"):
        ZealConfig.from_env()


def test_invalid_ebay_environment_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("EBAY_ENVIRONMENT", "staging")

    with pytest.raises(ValueError, match="EBAY_ENVIRONMENT"):
        ZealConfig.from_env()


def test_db_path_override_is_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_env(monkeypatch)
    db_path = tmp_path / "custom.db"
    monkeypatch.setenv("ZEAL_DB_PATH", str(db_path))

    config = ZealConfig.from_env()

    assert config.db_path == db_path
