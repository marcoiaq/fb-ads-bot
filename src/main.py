from __future__ import annotations

import asyncio
import datetime
import logging
import zoneinfo

from telegram.ext import Application

from config.settings import Settings
from src.bot.formatters import format_daily_report, format_error
from src.bot.handlers import register_handlers
from src.facebook.client import init_facebook_api
from src.facebook.insights import get_daily_insights
from src.utils.logger import setup_logger

logger: logging.Logger = None  # type: ignore[assignment]
settings: Settings = None  # type: ignore[assignment]


async def send_daily_report(context) -> None:
    """Scheduled job: send daily report to the configured chat."""
    logger.info("Running scheduled daily report")
    for acct in settings.ad_account_ids:
        try:
            data = get_daily_insights(acct)
            text = format_daily_report(acct, data)
        except Exception as e:
            logger.error("Daily report error for %s: %s", acct, e)
            text = format_error(f"Error for {acct}: {e}")
        await context.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            parse_mode="MarkdownV2",
        )
    logger.info("Daily report sent")


def main() -> None:
    global logger, settings

    logger = setup_logger()
    logger.info("Starting Facebook Ads Bot")

    settings = Settings.load()
    init_facebook_api(settings)

    app = Application.builder().token(settings.telegram_bot_token).build()

    register_handlers(app, settings)

    # Schedule daily report
    tz = zoneinfo.ZoneInfo(settings.timezone)
    report_time = datetime.time(
        hour=settings.report_time_hour, minute=0, tzinfo=tz
    )
    app.job_queue.run_daily(
        send_daily_report,
        time=report_time,
        name="daily_report",
    )
    logger.info(
        "Daily report scheduled at %02d:00 %s",
        settings.report_time_hour,
        settings.timezone,
    )

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
