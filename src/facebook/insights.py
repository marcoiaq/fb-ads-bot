from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from facebook_business.adobjects.adaccount import AdAccount

from src.facebook.client import safe_api_call

logger = logging.getLogger("fb-ads-bot")

INSIGHT_FIELDS = [
    "account_name",
    "impressions",
    "clicks",
    "cpm",
    "frequency",
    "spend",
    "actions",
    "cost_per_action_type",
]


def _extract_cpl(row: dict[str, Any]) -> float | None:
    """Extract cost-per-lead from cost_per_action_type."""
    for item in row.get("cost_per_action_type", []):
        if item.get("action_type") == "lead":
            return float(item["value"])
    return None


def _extract_leads(row: dict[str, Any]) -> int:
    """Extract lead count from actions."""
    for item in row.get("actions", []):
        if item.get("action_type") == "lead":
            return int(item["value"])
    return 0


def _parse_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_name": row.get("account_name", "Unknown"),
        "impressions": int(row.get("impressions", 0)),
        "clicks": int(row.get("clicks", 0)),
        "cpm": float(row.get("cpm", 0)),
        "frequency": float(row.get("frequency", 0)),
        "spend": float(row.get("spend", 0)),
        "leads": _extract_leads(row),
        "cpl": _extract_cpl(row),
        "date_start": row.get("date_start", ""),
        "date_stop": row.get("date_stop", ""),
    }


def get_daily_insights(account_id: str) -> dict[str, Any] | None:
    """Fetch yesterday's aggregated insights for an ad account."""
    account = AdAccount(account_id)
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "time_range": {"since": yesterday, "until": yesterday},
        "level": "account",
    }

    rows = safe_api_call(
        account.get_insights, fields=INSIGHT_FIELDS, params=params
    )
    data = list(rows)
    if not data:
        return None

    return _parse_row(data[0])


def get_comparison_insights(
    account_id: str, days: int = 7
) -> dict[str, dict[str, Any] | None]:
    """Fetch current period vs previous period insights for comparison.

    Returns {"current": {...}, "previous": {...}} or None values if no data.
    """
    account = AdAccount(account_id)
    today = datetime.now().date()

    current_end = today - timedelta(days=1)
    current_start = current_end - timedelta(days=days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)

    result = {}
    for label, start, end in [
        ("current", current_start, current_end),
        ("previous", previous_start, previous_end),
    ]:
        params = {
            "time_range": {
                "since": start.strftime("%Y-%m-%d"),
                "until": end.strftime("%Y-%m-%d"),
            },
            "level": "account",
        }
        rows = safe_api_call(
            account.get_insights, fields=INSIGHT_FIELDS, params=params
        )
        data = list(rows)
        result[label] = _parse_row(data[0]) if data else None

    return result
