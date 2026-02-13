class FacebookBotError(Exception):
    """Base exception for the bot."""


class TokenExpiredError(FacebookBotError):
    """Access token has expired or is invalid."""


class RateLimitError(FacebookBotError):
    """API rate limit hit."""


class PermissionError_(FacebookBotError):
    """Insufficient permissions on the ad account."""


class InvalidAccountError(FacebookBotError):
    """Ad account ID is invalid or inaccessible."""
