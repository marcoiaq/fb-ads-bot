from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Daily Report", callback_data="cmd_report"),
                InlineKeyboardButton("📈 Weekly", callback_data="cmd_weekly"),
            ],
            [
                InlineKeyboardButton("🎯 Campaigns", callback_data="cmd_campaigns"),
            ],
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="cmd_help"),
            ],
        ]
    )


def account_selector(
    accounts: list[str], action: str
) -> InlineKeyboardMarkup:
    """Build account selector. action is prefixed to callback data."""
    buttons = [
        [InlineKeyboardButton(acct, callback_data=f"{action}_{acct}")]
        for acct in accounts
    ]
    buttons.append([InlineKeyboardButton("« Back", callback_data="cmd_start")])
    return InlineKeyboardMarkup(buttons)


def entity_list(
    items: list[dict[str, Any]],
    entity_type: str,
    parent_callback: str = "cmd_start",
) -> InlineKeyboardMarkup:
    """Build a list of campaigns/adsets/ads with status emojis."""
    buttons = []
    for item in items:
        emoji = "🟢" if item["status"] == "ACTIVE" else "🔴"
        label = f"{emoji} {item['name'][:30]}"
        cb = f"select_{entity_type}_{item['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])

    buttons.append(
        [InlineKeyboardButton("« Back", callback_data=parent_callback)]
    )
    return InlineKeyboardMarkup(buttons)


def entity_actions(
    entity_type: str, entity_id: str, current_status: str, parent_callback: str
) -> InlineKeyboardMarkup:
    """Action menu for a selected entity (pause/resume/budget)."""
    buttons = []

    if current_status == "ACTIVE":
        buttons.append(
            [
                InlineKeyboardButton(
                    "⏸ Pause",
                    callback_data=f"pause_{entity_type}_{entity_id}",
                )
            ]
        )
    elif current_status == "PAUSED":
        buttons.append(
            [
                InlineKeyboardButton(
                    "▶️ Resume",
                    callback_data=f"resume_{entity_type}_{entity_id}",
                )
            ]
        )

    if entity_type in ("campaign", "adset"):
        buttons.append(
            [
                InlineKeyboardButton(
                    "💰 Change Budget",
                    callback_data=f"budget_{entity_type}_{entity_id}",
                )
            ]
        )

    # Navigation into children
    if entity_type == "campaign":
        buttons.append(
            [
                InlineKeyboardButton(
                    "📂 Ad Sets",
                    callback_data=f"listadsets_{entity_id}",
                )
            ]
        )
    elif entity_type == "adset":
        buttons.append(
            [
                InlineKeyboardButton(
                    "📂 Ads",
                    callback_data=f"listads_{entity_id}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton("« Back", callback_data=parent_callback)]
    )
    return InlineKeyboardMarkup(buttons)


def confirm_action(
    action: str, entity_type: str, entity_id: str, cancel_callback: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data=f"confirm_{action}_{entity_type}_{entity_id}",
                ),
                InlineKeyboardButton("❌ Cancel", callback_data=cancel_callback),
            ],
        ]
    )
