from __future__ import annotations

from typing import Any


def format_daily_report(account_id: str, data: dict[str, Any] | None) -> str:
    if data is None:
        return f"*{_esc(account_id)}*\nNo data for yesterday\\."

    name = _esc(data["account_name"])
    impressions = _esc(f"{data['impressions']:,}")
    clicks = _esc(f"{data['clicks']:,}")
    cpm = _esc(f"${data['cpm']:.2f}")
    frequency = _esc(f"{data['frequency']:.2f}")
    spend = _esc(f"${data['spend']:.2f}")
    leads = _esc(str(data['leads']))

    lines = [
        f"*{name}*  \\(`{_esc(account_id)}`\\)",
        f"Date: {_esc(data['date_start'])}",
        "",
        f"Impressions: *{impressions}*",
        f"Clicks: *{clicks}*",
        f"CPM: *{cpm}*",
        f"Frequency: *{frequency}*",
        f"Spend: *{spend}*",
        f"Leads: *{leads}*",
    ]
    if data["cpl"] is not None:
        cpl = _esc(f"${data['cpl']:.2f}")
        lines.append(f"CPL: *{cpl}*")
    else:
        lines.append("CPL: *N/A* \\(no leads\\)")

    return "\n".join(lines)


def format_weekly_report(
    account_id: str, comparison: dict[str, dict[str, Any] | None]
) -> str:
    current = comparison.get("current")
    previous = comparison.get("previous")

    if current is None:
        return f"*{_esc(account_id)}*\nNo data for current period\\."

    name = _esc(current["account_name"])
    header = f"*{name}* — 7\\-day summary"

    metrics = [
        ("Impressions", "impressions", False),
        ("Clicks", "clicks", False),
        ("CPM", "cpm", True),
        ("Frequency", "frequency", False),
        ("Spend", "spend", True),
        ("Leads", "leads", False),
        ("CPL", "cpl", True),
    ]

    lines = [header, f"{_esc(current['date_start'])} → {_esc(current['date_stop'])}", ""]
    for label, key, is_dollar in metrics:
        cur_val = current.get(key)
        prev_val = previous.get(key) if previous else None
        lines.append(_metric_line(label, cur_val, prev_val, is_dollar))

    return "\n".join(lines)


def format_entity_info(entity: dict[str, Any], entity_type: str) -> str:
    status_emoji = "🟢" if entity["status"] == "ACTIVE" else "🔴"
    name = _esc(entity["name"])
    lines = [f"{status_emoji} *{name}*", f"Status: {_esc(entity['status'])}"]

    if entity_type in ("campaign", "adset"):
        db = entity.get("daily_budget")
        lb = entity.get("lifetime_budget")
        if db is not None:
            lines.append(f"Daily budget: {_esc(f'${db:.2f}')}")
        if lb is not None:
            lines.append(f"Lifetime budget: {_esc(f'${lb:.2f}')}")

    if entity_type == "campaign" and entity.get("objective"):
        lines.append(f"Objective: {_esc(entity['objective'])}")

    return "\n".join(lines)


def format_success(msg: str) -> str:
    return f"✅ {_esc(msg)}"


def format_error(msg: str) -> str:
    return f"❌ {_esc(msg)}"


# --- Helpers ---


def _esc(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    out = []
    for ch in str(text):
        if ch in special:
            out.append(f"\\{ch}")
        else:
            out.append(ch)
    return "".join(out)


def _metric_line(
    label: str, cur: float | int | None, prev: float | int | None, is_dollar: bool
) -> str:
    if cur is None:
        return f"{label}: N/A"

    if is_dollar:
        cur_str = _esc(f"${cur:.2f}")
    else:
        cur_str = _esc(f"{cur:,.2f}" if isinstance(cur, float) else f"{cur:,}")

    if prev is not None and prev != 0:
        pct = ((cur - prev) / prev) * 100
        arrow = "📈" if pct > 0 else "📉" if pct < 0 else "➡️"
        pct_str = _esc(f"{pct:+.1f}")
        return f"{label}: *{cur_str}* {arrow} {pct_str}%"

    return f"{label}: *{cur_str}*"
