class RateLimitError(Exception):
    """429 от HH.ru — нужен для retry."""

    pass
