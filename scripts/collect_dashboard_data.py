#!/usr/bin/env python3
"""Fetch Facebook Ads insights and write dashboard/data.json for the static dashboard.

Keeps the last 7 days of data per account. Intended to be run daily by GitHub Actions.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings
from src.facebook.client import init_facebook_api
from src.facebook.insights import get_comparison_insights, get_daily_insights

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).resolve().parent.parent / "dashboard" / "data.json"
MAX_DAYS = 7


def load_existing() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"last_updated": None, "accounts": {}}


def save(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2) + "\n")


def _period_dict(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "impressions": row["impressions"],
        "clicks": row["clicks"],
        "cpm": row["cpm"],
        "frequency": row["frequency"],
        "spend": row["spend"],
        "leads": row["leads"],
        "cpl": row["cpl"],
    }


def _build_summary(comparison: dict) -> dict:
    return {
        "current": _period_dict(comparison.get("current")),
        "previous": _period_dict(comparison.get("previous")),
    }


def main() -> None:
    settings = Settings.load()
    init_facebook_api(settings)

    data = load_existing()

    for account_id in settings.ad_account_ids:
        logger.info("Fetching insights for %s ...", account_id)
        try:
            row = get_daily_insights(account_id)
            if row is None:
                logger.warning("No data returned for %s", account_id)
                continue

            day_entry = {
                "date": row["date_start"],
                "impressions": row["impressions"],
                "clicks": row["clicks"],
                "cpm": row["cpm"],
                "frequency": row["frequency"],
                "spend": row["spend"],
                "leads": row["leads"],
                "cpl": row["cpl"],
            }

            account = data["accounts"].setdefault(account_id, {
                "name": row["account_name"],
                "days": [],
                "summary": None,
            })
            account["name"] = row["account_name"]

            # Deduplicate by date (replace existing entry for the same date)
            account["days"] = [
                d for d in account["days"] if d["date"] != day_entry["date"]
            ]
            account["days"].append(day_entry)

            # Sort ascending and keep last N days
            account["days"].sort(key=lambda d: d["date"])
            account["days"] = account["days"][-MAX_DAYS:]

            # Fetch 7-day period comparison for KPI cards
            logger.info("Fetching 7-day comparison for %s ...", account_id)
            comparison = get_comparison_insights(account_id)
            account["summary"] = _build_summary(comparison)

        except Exception:
            logger.exception("Failed to process account %s", account_id)

    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    save(data)
    logger.info("Dashboard data written to %s", DATA_FILE)


if __name__ == "__main__":
    main()
