"""Errors shared by the forecast providers and the callers that catch them (kept apart so the providers can import them without
importing each other)."""


class ForecastUnavailable(Exception):
    """The provider could not be reached or returned something unusable."""


class InvalidCoordinates(ValueError):
    pass
