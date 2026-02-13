from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from config.settings import Settings
from src.bot import formatters, keyboards
from src.facebook import insights, management

logger = logging.getLogger("fb-ads-bot")


def make_callback_handler(settings: Settings) -> CallbackQueryHandler:
    async def handle_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        await query.answer()

        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id != settings.telegram_chat_id:
            return

        data = query.data
        logger.info("Callback: %s", data)

        # --- Menu commands ---
        if data == "cmd_start":
            await query.edit_message_text(
                "👋 *Facebook Ads Bot*\n\nChoose an action:",
                reply_markup=keyboards.main_menu(),
                parse_mode="MarkdownV2",
            )
            return

        if data == "cmd_report":
            await query.edit_message_text("Fetching daily report\\.\\.\\.", parse_mode="MarkdownV2")
            for acct in settings.ad_account_ids:
                try:
                    d = insights.get_daily_insights(acct)
                    text = formatters.format_daily_report(acct, d)
                except Exception as e:
                    text = formatters.format_error(f"Error for {acct}: {e}")
                await query.message.reply_text(text, parse_mode="MarkdownV2")
            return

        if data == "cmd_weekly":
            await query.edit_message_text("Fetching weekly comparison\\.\\.\\.", parse_mode="MarkdownV2")
            for acct in settings.ad_account_ids:
                try:
                    comp = insights.get_comparison_insights(acct, days=7)
                    text = formatters.format_weekly_report(acct, comp)
                except Exception as e:
                    text = formatters.format_error(f"Error for {acct}: {e}")
                await query.message.reply_text(text, parse_mode="MarkdownV2")
            return

        if data == "cmd_campaigns":
            accts = settings.ad_account_ids
            if len(accts) == 1:
                await _show_campaigns_cb(query, context, accts[0])
            else:
                await query.edit_message_text(
                    "Select an account:",
                    reply_markup=keyboards.account_selector(
                        accts, "selacct_campaigns"
                    ),
                )
            return

        if data == "cmd_help":
            text = (
                "*Commands*\n\n"
                "/start — Main menu\n"
                "/report — Yesterday's metrics\n"
                "/weekly — 7\\-day comparison\n"
                "/campaigns — Manage campaigns\n"
                "/help — This message"
            )
            await query.edit_message_text(
                text,
                reply_markup=keyboards.main_menu(),
                parse_mode="MarkdownV2",
            )
            return

        # --- Account selection ---
        if data.startswith("selacct_campaigns_"):
            account_id = data.replace("selacct_campaigns_", "")
            await _show_campaigns_cb(query, context, account_id)
            return

        # --- Entity selection ---
        if data.startswith("select_"):
            parts = data.split("_", 2)  # select, type, id
            if len(parts) == 3:
                entity_type, entity_id = parts[1], parts[2]
                await _show_entity_actions(query, context, entity_type, entity_id)
            return

        # --- List adsets for a campaign ---
        if data.startswith("listadsets_"):
            campaign_id = data.replace("listadsets_", "")
            await _show_adsets(query, context, campaign_id)
            return

        # --- List ads for an adset ---
        if data.startswith("listads_"):
            adset_id = data.replace("listads_", "")
            await _show_ads(query, context, adset_id)
            return

        # --- Pause ---
        if data.startswith("pause_"):
            parts = data.split("_", 2)
            entity_type, entity_id = parts[1], parts[2]
            cancel_cb = f"select_{entity_type}_{entity_id}"
            await query.edit_message_text(
                f"Pause this {entity_type}?",
                reply_markup=keyboards.confirm_action(
                    "pause", entity_type, entity_id, cancel_cb
                ),
            )
            return

        # --- Resume ---
        if data.startswith("resume_"):
            parts = data.split("_", 2)
            entity_type, entity_id = parts[1], parts[2]
            cancel_cb = f"select_{entity_type}_{entity_id}"
            await query.edit_message_text(
                f"Resume this {entity_type}?",
                reply_markup=keyboards.confirm_action(
                    "resume", entity_type, entity_id, cancel_cb
                ),
            )
            return

        # --- Budget prompt ---
        if data.startswith("budget_"):
            parts = data.split("_", 2)
            entity_type, entity_id = parts[1], parts[2]
            context.user_data["pending_budget"] = {
                "entity_type": entity_type,
                "entity_id": entity_id,
            }
            await query.edit_message_text(
                f"Send the new daily budget amount in dollars (e.g. 50 or 25.50):"
            )
            return

        # --- Confirm actions ---
        if data.startswith("confirm_"):
            remainder = data[len("confirm_"):]
            await _handle_confirm(query, context, remainder)
            return

    return CallbackQueryHandler(handle_callback)


async def _show_campaigns_cb(query, context, account_id: str) -> None:
    try:
        camps = management.list_campaigns(account_id)
    except Exception as e:
        await query.edit_message_text(
            formatters.format_error(str(e)), parse_mode="MarkdownV2"
        )
        return

    if not camps:
        await query.edit_message_text("No campaigns found\\.", parse_mode="MarkdownV2")
        return

    context.user_data["current_account"] = account_id
    await query.edit_message_text(
        f"Campaigns for `{formatters._esc(account_id)}`:",
        reply_markup=keyboards.entity_list(camps, "campaign"),
        parse_mode="MarkdownV2",
    )


async def _show_entity_actions(query, context, entity_type: str, entity_id: str) -> None:
    """Show action menu for a campaign/adset/ad."""
    try:
        if entity_type == "campaign":
            items = management.list_campaigns(context.user_data.get("current_account", ""))
        elif entity_type == "adset":
            # Find the parent campaign from user_data
            items = management.list_adsets(context.user_data.get("current_campaign", ""))
        else:
            items = management.list_ads(context.user_data.get("current_adset", ""))

        entity = next((e for e in items if e["id"] == entity_id), None)
    except Exception as e:
        await query.edit_message_text(
            formatters.format_error(str(e)), parse_mode="MarkdownV2"
        )
        return

    if entity is None:
        await query.edit_message_text("Entity not found\\.", parse_mode="MarkdownV2")
        return

    # Store the current ID for navigation
    if entity_type == "campaign":
        context.user_data["current_campaign"] = entity_id
    elif entity_type == "adset":
        context.user_data["current_adset"] = entity_id

    parent_cb = "cmd_campaigns"
    if entity_type == "adset":
        parent_cb = f"listadsets_{context.user_data.get('current_campaign', '')}"
    elif entity_type == "ad":
        parent_cb = f"listads_{context.user_data.get('current_adset', '')}"

    info = formatters.format_entity_info(entity, entity_type)
    await query.edit_message_text(
        info,
        reply_markup=keyboards.entity_actions(
            entity_type, entity_id, entity["status"], parent_cb
        ),
        parse_mode="MarkdownV2",
    )


async def _show_adsets(query, context, campaign_id: str) -> None:
    context.user_data["current_campaign"] = campaign_id
    try:
        adsets = management.list_adsets(campaign_id)
    except Exception as e:
        await query.edit_message_text(
            formatters.format_error(str(e)), parse_mode="MarkdownV2"
        )
        return

    if not adsets:
        await query.edit_message_text("No ad sets found\\.", parse_mode="MarkdownV2")
        return

    parent_cb = f"select_campaign_{campaign_id}"
    await query.edit_message_text(
        "Ad Sets:",
        reply_markup=keyboards.entity_list(adsets, "adset", parent_cb),
    )


async def _show_ads(query, context, adset_id: str) -> None:
    context.user_data["current_adset"] = adset_id
    try:
        ads = management.list_ads(adset_id)
    except Exception as e:
        await query.edit_message_text(
            formatters.format_error(str(e)), parse_mode="MarkdownV2"
        )
        return

    if not ads:
        await query.edit_message_text("No ads found\\.", parse_mode="MarkdownV2")
        return

    parent_cb = f"select_adset_{adset_id}"
    await query.edit_message_text(
        "Ads:",
        reply_markup=keyboards.entity_list(ads, "ad", parent_cb),
    )


async def _handle_confirm(query, context, remainder: str) -> None:
    """Handle confirm_<action>_<entity_type>_<entity_id>."""
    parts = remainder.split("_", 2)
    if len(parts) < 3:
        return

    action, entity_type, entity_id = parts[0], parts[1], parts[2]

    try:
        if action == "pause":
            management.update_status(entity_type, entity_id, "PAUSED")
            await query.edit_message_text(
                formatters.format_success(
                    f"{entity_type.title()} paused successfully"
                ),
                parse_mode="MarkdownV2",
            )
        elif action == "resume":
            management.update_status(entity_type, entity_id, "ACTIVE")
            await query.edit_message_text(
                formatters.format_success(
                    f"{entity_type.title()} resumed successfully"
                ),
                parse_mode="MarkdownV2",
            )
        elif action == "setbudget":
            amount = context.user_data.pop("confirm_budget_amount", None)
            if amount is None:
                await query.edit_message_text(
                    formatters.format_error("Budget amount expired. Please try again."),
                    parse_mode="MarkdownV2",
                )
                return
            management.update_budget(entity_type, entity_id, amount)
            await query.edit_message_text(
                formatters.format_success(
                    f"Budget updated to ${amount:.2f}"
                ),
                parse_mode="MarkdownV2",
            )
        else:
            await query.edit_message_text("Unknown action\\.", parse_mode="MarkdownV2")
    except Exception as e:
        await query.edit_message_text(
            formatters.format_error(str(e)), parse_mode="MarkdownV2"
        )
