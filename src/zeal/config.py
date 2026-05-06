from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv

from zeal.db.connection import DEFAULT_DB_PATH

EbayMode = Literal["synthetic", "live"]
EbayEnvironment = Literal["production", "sandbox"]


@dataclass(frozen=True)
class ZealConfig:
    ebay_mode: EbayMode
    ebay_client_id: str | None
    ebay_client_secret: str | None
    ebay_environment: EbayEnvironment
    db_path: Path

    @classmethod
    def from_env(cls) -> ZealConfig:
        load_dotenv()

        ebay_mode = _read_ebay_mode()
        ebay_environment = _read_ebay_environment()
        ebay_client_id = _optional_env("EBAY_CLIENT_ID")
        ebay_client_secret = _optional_env("EBAY_CLIENT_SECRET")
        db_path = Path(os.environ.get("ZEAL_DB_PATH", str(DEFAULT_DB_PATH)))

        if ebay_mode == "live":
            missing = [
                name
                for name, value in (
                    ("EBAY_CLIENT_ID", ebay_client_id),
                    ("EBAY_CLIENT_SECRET", ebay_client_secret),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"Missing required live eBay credential(s): {', '.join(missing)}")

        return cls(
            ebay_mode=ebay_mode,
            ebay_client_id=ebay_client_id,
            ebay_client_secret=ebay_client_secret,
            ebay_environment=ebay_environment,
            db_path=db_path,
        )


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return None
    return value


def _read_ebay_mode() -> EbayMode:
    value = os.environ.get("ZEAL_EBAY_MODE", "synthetic").strip().lower()
    if value not in {"synthetic", "live"}:
        raise ValueError("ZEAL_EBAY_MODE must be 'synthetic' or 'live'")
    return cast(EbayMode, value)


def _read_ebay_environment() -> EbayEnvironment:
    value = os.environ.get("EBAY_ENVIRONMENT", "production").strip().lower()
    if value not in {"production", "sandbox"}:
        raise ValueError("EBAY_ENVIRONMENT must be 'production' or 'sandbox'")
    return cast(EbayEnvironment, value)
