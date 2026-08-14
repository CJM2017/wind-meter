"""Application error types."""


class CapeRideError(Exception):
    """Base error for expected application failures."""


class ConfigurationError(CapeRideError):
    """Raised when required local configuration is missing or invalid."""


class ProviderError(CapeRideError):
    """Raised when an external provider rejects or cannot satisfy a request."""


class SchemaError(CapeRideError):
    """Raised when a provider response no longer matches the known contract."""

