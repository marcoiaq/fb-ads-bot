from __future__ import annotations

import logging
from typing import Any

from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.campaign import Campaign

from src.facebook.client import safe_api_call

logger = logging.getLogger("fb-ads-bot")

# --- Listing ---


def list_campaigns(account_id: str) -> list[dict[str, Any]]:
    account = AdAccount(account_id)
    fields = ["name", "status", "daily_budget", "lifetime_budget", "objective"]
    items = safe_api_call(account.get_campaigns, fields=fields)
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "status": c["status"],
            "daily_budget": _cents_to_dollars(c.get("daily_budget")),
            "lifetime_budget": _cents_to_dollars(c.get("lifetime_budget")),
            "objective": c.get("objective", ""),
        }
        for c in items
    ]


def list_adsets(campaign_id: str) -> list[dict[str, Any]]:
    campaign = Campaign(campaign_id)
    fields = ["name", "status", "daily_budget", "lifetime_budget", "campaign_id"]
    items = safe_api_call(campaign.get_ad_sets, fields=fields)
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "status": s["status"],
            "daily_budget": _cents_to_dollars(s.get("daily_budget")),
            "lifetime_budget": _cents_to_dollars(s.get("lifetime_budget")),
            "campaign_id": s.get("campaign_id", ""),
        }
        for s in items
    ]


def list_ads(adset_id: str) -> list[dict[str, Any]]:
    adset = AdSet(adset_id)
    fields = ["name", "status", "adset_id"]
    items = safe_api_call(adset.get_ads, fields=fields)
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "status": a["status"],
            "adset_id": a.get("adset_id", ""),
        }
        for a in items
    ]


# --- Status updates ---

_OBJ_MAP = {
    "campaign": Campaign,
    "adset": AdSet,
    "ad": Ad,
}


def update_status(entity_type: str, entity_id: str, new_status: str) -> None:
    """Set status to ACTIVE or PAUSED.

    entity_type: 'campaign', 'adset', or 'ad'
    """
    cls = _OBJ_MAP[entity_type]
    obj = cls(entity_id)
    obj[cls.Field.status] = new_status
    safe_api_call(obj.remote_update)
    logger.info("Updated %s %s status to %s", entity_type, entity_id, new_status)


# --- Budget updates ---


def update_budget(
    entity_type: str, entity_id: str, daily_budget_dollars: float
) -> None:
    """Update daily budget. Accepts dollars, converts to cents for the API."""
    if entity_type not in ("campaign", "adset"):
        raise ValueError("Budget can only be set on campaigns or adsets")

    cls = _OBJ_MAP[entity_type]
    obj = cls(entity_id)
    budget_cents = str(int(round(daily_budget_dollars * 100)))
    obj[cls.Field.daily_budget] = budget_cents
    safe_api_call(obj.remote_update)
    logger.info(
        "Updated %s %s daily budget to $%.2f",
        entity_type,
        entity_id,
        daily_budget_dollars,
    )


def _cents_to_dollars(val: str | None) -> float | None:
    if val is None:
        return None
    return int(val) / 100.0
