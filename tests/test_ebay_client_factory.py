import httpx

from zeal.config import ZealConfig
from zeal.db.connection import DEFAULT_DB_PATH
from zeal.ingestion.ebay_client import SyntheticEbayClient
from zeal.ingestion.ebay_client_factory import create_ebay_client
from zeal.ingestion.ebay_marketplace_insights_client import EbayMarketplaceInsightsClient


def _config(
    *,
    mode: str = "synthetic",
    environment: str = "production",
    client_id: str | None = None,
    client_secret: str | None = None,
) -> ZealConfig:
    return ZealConfig(
        ebay_mode=mode,
        ebay_client_id=client_id,
        ebay_client_secret=client_secret,
        ebay_environment=environment,
        db_path=DEFAULT_DB_PATH,
    )


def test_synthetic_mode_returns_synthetic_client_regardless_of_credentials() -> None:
    client = create_ebay_client(
        config=_config(mode="synthetic", client_id="id", client_secret="secret"),
        http_client=httpx.AsyncClient(),
    )

    assert isinstance(client, SyntheticEbayClient)


def test_live_mode_with_credentials_returns_marketplace_insights_client() -> None:
    http_client = httpx.AsyncClient()

    client = create_ebay_client(
        config=_config(mode="live", client_id="id", client_secret="secret"),
        http_client=http_client,
    )

    assert isinstance(client, EbayMarketplaceInsightsClient)


def test_live_mode_constructs_token_manager_with_environment() -> None:
    http_client = httpx.AsyncClient()

    client = create_ebay_client(
        config=_config(
            mode="live",
            environment="sandbox",
            client_id="id",
            client_secret="secret",
        ),
        http_client=http_client,
    )

    assert isinstance(client, EbayMarketplaceInsightsClient)
    assert client._base_url == "https://api.sandbox.ebay.com"
    assert client._token_manager._token_url == "https://api.sandbox.ebay.com/identity/v1/oauth2/token"


def test_live_mode_uses_passed_http_client() -> None:
    http_client = httpx.AsyncClient()

    client = create_ebay_client(
        config=_config(mode="live", client_id="id", client_secret="secret"),
        http_client=http_client,
    )

    assert isinstance(client, EbayMarketplaceInsightsClient)
    assert client._http is http_client
    assert client._token_manager._http is http_client
