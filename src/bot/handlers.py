from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config.settings import Settings
from src.bot import formatters, keyboards
from src.facebook import insights, management

logger = logging.getLogger("fb-ads-bot")


def _authorized(settings: Settings):
    """Decorator: silently ignore unauthorized users."""

    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id != settings.telegram_chat_id:
                logger.warning("Unauthorized access attempt from chat_id=%s", chat_id)
                return
            return await func(update, context)

        return wrapper

    return decorator


def register_handlers(app, settings: Settings) -> None:
    """Register all command handlers on the Application."""
    from telegram.ext import CommandHandler, MessageHandler, filters

    from src.bot.callbacks import make_callback_handler

    auth = _authorized(settings)

    @auth
    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 *Facebook Ads Bot*\n\nChoose an action:",
            reply_markup=keyboards.main_menu(),
            parse_mode="MarkdownV2",
        )

    @auth
    async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Fetching daily report\\.\\.\\.", parse_mode="MarkdownV2")
        for acct in settings.ad_account_ids:
            try:
                data = insights.get_daily_insights(acct)
                text = formatters.format_daily_report(acct, data)
            except Exception as e:
                text = formatters.format_error(f"Error for {acct}: {e}")
            await update.message.reply_text(text, parse_mode="MarkdownV2")

    @auth
    async def weekly_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Fetching weekly comparison\\.\\.\\.", parse_mode="MarkdownV2")
        for acct in settings.ad_account_ids:
            try:
                comp = insights.get_comparison_insights(acct, days=7)
                text = formatters.format_weekly_report(acct, comp)
            except Exception as e:
                text = formatters.format_error(f"Error for {acct}: {e}")
            await update.message.reply_text(text, parse_mode="MarkdownV2")

    @auth
    async def campaigns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        accts = settings.ad_account_ids
        if len(accts) == 1:
            await _show_campaigns(update, context, accts[0])
        else:
            await update.message.reply_text(
                "Select an account:",
                reply_markup=keyboards.account_selector(accts, "selacct_campaigns"),
            )

    @auth
    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "*Commands*\n\n"
            "/start — Main menu\n"
            "/report — Yesterday's metrics\n"
            "/weekly — 7\\-day comparison\n"
            "/campaigns — Manage campaigns\n"
            "/help — This message"
        )
        await update.message.reply_text(text, parse_mode="MarkdownV2")

    @auth
    async def budget_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text replies for budget input."""
        pending = context.user_data.get("pending_budget")
        if not pending:
            return

        text = update.message.text.strip().replace("$", "").replace(",", "")
        try:
            amount = float(text)
        except ValueError:
            await update.message.reply_text(
                formatters.format_error("Invalid amount. Send a number like 50 or 25.50"),
                parse_mode="MarkdownV2",
            )
            return

        if amount <= 0 or amount > 100000:
            await update.message.reply_text(
                formatters.format_error("Amount must be between $0.01 and $100,000"),
                parse_mode="MarkdownV2",
            )
            return

        entity_type = pending["entity_type"]
        entity_id = pending["entity_id"]
        context.user_data.pop("pending_budget", None)

        cancel_cb = f"select_{entity_type}_{entity_id}"
        # Store amount in user_data so callback doesn't need it in the data string
        context.user_data["confirm_budget_amount"] = amount
        await update.message.reply_text(
            f"Set daily budget to *${amount:.2f}*?",
            reply_markup=keyboards.confirm_action(
                "setbudget", entity_type, entity_id, cancel_cb
            ),
            parse_mode="MarkdownV2",
        )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    app.add_handler(CommandHandler("weekly", weekly_cmd))
    app.add_handler(CommandHandler("campaigns", campaigns_cmd))
    app.add_handler(CommandHandler("adsets", campaigns_cmd))  # alias
    app.add_handler(CommandHandler("ads", campaigns_cmd))  # alias
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(make_callback_handler(settings))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, budget_text_handler)
    )


async def _show_campaigns(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: str
) -> None:
    try:
        camps = management.list_campaigns(account_id)
    except Exception as e:
        await update.message.reply_text(
            formatters.format_error(str(e)), parse_mode="MarkdownV2"
        )
        return

    if not camps:
        await update.message.reply_text("No campaigns found\\.", parse_mode="MarkdownV2")
        return

    context.user_data["current_account"] = account_id
    await update.message.reply_text(
        f"Campaigns for `{formatters._esc(account_id)}`:",
        reply_markup=keyboards.entity_list(camps, "campaign"),
        parse_mode="MarkdownV2",
    )
