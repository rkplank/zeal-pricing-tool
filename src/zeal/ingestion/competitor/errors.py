class CompetitorClientError(Exception):
    """Base for all competitor client errors."""


class CompetitorRateLimitError(CompetitorClientError):
    """Rate limit exhausted after retries."""


class CompetitorServerError(CompetitorClientError):
    """Competitor server returned a 5xx response after retries."""


class CompetitorNetworkError(CompetitorClientError):
    """Network-level failure after retries."""
