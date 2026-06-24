from __future__ import annotations

from datetime import datetime
from typing import Protocol

from zeal.models.competitor import CompetitorObservation


class CompetitorClient(Protocol):
    """Interface implemented by live competitor scrapers and test doubles."""

    async def fetch_observations(
        self,
        *,
        merchant_id: str,
        source_key: int,
        observed_at: datetime,
    ) -> list[CompetitorObservation]:
        """Return all competitor observations for one merchant.

        source_key is the source-specific numeric identifier. For CardCash this
        is the id field from merchantsBuy.sortedByName, stored on the Zeal
        merchant as merchants.cardcash_id (e.g. 27 for Home Depot). Typed as int
        for v1 with CardCash as the sole source; generalises to str | int when
        additional sources with non-numeric identifiers are added.

        Never raises on per-merchant parse or network failure — those become
        availability='no_data' observations in the returned list. Raises
        CompetitorClientError only on run-aborting failures such as session
        bootstrap failure, catalog parse failure, or cart create failure.
        """
        ...

    @property
    def source_name(self) -> str:
        """Identifier matching competitor_sources.source_name in the DB."""
        ...
