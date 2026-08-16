"""Domain exceptions with messages safe to display to CLI users."""


class ListarrError(Exception):
    """Base error for expected Listarr failures."""


class ConfigurationError(ListarrError):
    """Raised when configuration is missing or invalid."""


class APIError(ListarrError):
    """Raised when an Arr or MDBList request fails."""


class RateLimitError(APIError):
    """Raised when MDBList's request allowance is exhausted."""
