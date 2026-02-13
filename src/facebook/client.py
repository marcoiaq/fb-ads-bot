from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError

from src.utils.errors import (
    FacebookBotError,
    InvalidAccountError,
    PermissionError_,
    RateLimitError,
    TokenExpiredError,
)

if TYPE_CHECKING:
    from config.settings import Settings

logger = logging.getLogger("fb-ads-bot")


def init_facebook_api(settings: Settings) -> FacebookAdsApi:
    api = FacebookAdsApi.init(
        app_id=settings.facebook_app_id,
        app_secret=settings.facebook_app_secret,
        access_token=settings.facebook_access_token,
    )
    logger.info("Facebook Ads API initialized")
    return api


def classify_error(exc: FacebookRequestError) -> FacebookBotError:
    code = exc.api_error_code()
    subcode = exc.api_error_subcode() or 0
    msg = exc.api_error_message() or str(exc)

    # Token expired / invalid
    if code == 190 or subcode in (463, 467):
        return TokenExpiredError(f"Token error ({code}/{subcode}): {msg}")

    # Rate limit
    if code in (4, 17, 32, 613):
        return RateLimitError(f"Rate limit ({code}): {msg}")

    # Permission
    if code in (10, 200, 273, 294):
        return PermissionError_(f"Permission error ({code}): {msg}")

    # Invalid account
    if code == 100:
        return InvalidAccountError(f"Invalid request ({code}): {msg}")

    return FacebookBotError(f"Facebook API error ({code}): {msg}")


def safe_api_call(func, *args, **kwargs):
    """Wraps a Facebook API call, translating errors to custom exceptions."""
    try:
        return func(*args, **kwargs)
    except FacebookRequestError as e:
        raise classify_error(e) from e
