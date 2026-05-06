class EbayClientError(Exception):
    """Base for all eBay client errors."""


class EbayAuthError(EbayClientError):
    """Authentication failed or token was rejected."""


class EbayRateLimitError(EbayClientError):
    """Rate limit exhausted after retries."""


class EbayServerError(EbayClientError):
    """eBay returned a 5xx response after retries."""


class EbayNetworkError(EbayClientError):
    """Network-level failure after retries."""
