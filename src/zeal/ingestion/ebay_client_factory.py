from __future__ import annotations

import httpx

from zeal.config import ZealConfig
from zeal.ingestion.ebay_client import EbayClient, SyntheticEbayClient
from zeal.ingestion.ebay_marketplace_insights_client import EbayMarketplaceInsightsClient
from zeal.ingestion.ebay_oauth import EbayTokenManager


def create_ebay_client(*, config: ZealConfig, http_client: httpx.AsyncClient) -> EbayClient:
    if config.ebay_mode == "synthetic":
        return SyntheticEbayClient()

    if config.ebay_client_id is None or config.ebay_client_secret is None:
        raise ValueError("Live eBay mode requires EBAY_CLIENT_ID and EBAY_CLIENT_SECRET")

    token_manager = EbayTokenManager(
        client_id=config.ebay_client_id,
        client_secret=config.ebay_client_secret,
        environment=config.ebay_environment,
        http_client=http_client,
    )
    return EbayMarketplaceInsightsClient(
        token_manager=token_manager,
        environment=config.ebay_environment,
        http_client=http_client,
    )
