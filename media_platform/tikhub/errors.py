class TikHubError(Exception):
    """Base error for TikHub crawler failures."""


class TikHubConfigError(TikHubError):
    """TikHub configuration is missing or invalid."""


class TikHubAuthError(TikHubError):
    """TikHub rejected the configured token."""


class TikHubRateLimitError(TikHubError):
    """TikHub rate limit was reached."""


class TikHubValidationError(TikHubError):
    """TikHub rejected request parameters."""


class TikHubUpstreamError(TikHubError):
    """TikHub or the network failed after retries."""


class TikHubCapabilityError(TikHubError):
    """Requested capability is not supported by the registry."""
