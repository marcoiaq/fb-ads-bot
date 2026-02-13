#!/usr/bin/env python3
"""Standalone script to fetch Facebook Ads insights and send reports via Telegram.

Intended to be run by GitHub Actions on a schedule, but works locally too.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from config.settings import Settings
from src.facebook.client import init_facebook_api
from src.facebook.insights import get_comparison_insights, get_daily_insights
from src.bot.formatters import format_daily_report, format_weekly_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def send_telegram(token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
    }, timeout=30)
    resp.raise_for_status()
    logger.info("Telegram message sent (chat_id=%s)", chat_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Facebook Ads report to Telegram")
    parser.add_argument("--weekly", action="store_true", help="Send 7-day comparison report instead of daily")
    args = parser.parse_args()

    settings = Settings.load()
    init_facebook_api(settings)

    for account_id in settings.ad_account_ids:
        logger.info("Fetching insights for %s ...", account_id)
        try:
            if args.weekly:
                comparison = get_comparison_insights(account_id)
                text = format_weekly_report(account_id, comparison)
            else:
                data = get_daily_insights(account_id)
                text = format_daily_report(account_id, data)

            send_telegram(settings.telegram_bot_token, settings.telegram_chat_id, text)
        except Exception:
            logger.exception("Failed to process account %s", account_id)

    logger.info("Done.")


if __name__ == "__main__":
    main()
