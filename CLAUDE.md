# fb-ads-bot

Telegram bot for managing Facebook Ads campaigns for med-spa clients. Provides daily/weekly reports, campaign management, Notion-synced client data, and AI ad generation.

## Architecture

```
config/settings.py      — Settings dataclass, loads .env
src/main.py             — Entry point (Application builder + scheduler)
src/bot/handlers.py     — Command handlers (/start, /report, /sync, etc.)
src/bot/callbacks.py    — Inline button callback handlers
src/bot/keyboards.py    — InlineKeyboardMarkup builders
src/bot/formatters.py   — MarkdownV2 formatting helpers
src/bot/medspa.py       — State management for ad generation (reads skill state)
src/bot/notion_sync.py  — Notion API sync for clients & offers
src/facebook/insights.py   — Facebook Marketing API: metrics
src/facebook/management.py — Facebook Marketing API: campaign/adset/ad CRUD
dashboard/              — Static HTML dashboard
scripts/                — LaunchAgent plist (macOS auto-start)
```

## Running the bot

```bash
# Activate venv and run
venv/bin/python -m src.main

# Run in background
nohup venv/bin/python -m src.main > /tmp/fb-ads-bot.log 2>&1 &

# Restart
kill $(pgrep -f 'src.main') && nohup venv/bin/python -m src.main > /tmp/fb-ads-bot.log 2>&1 &

# Check if running
pgrep -fa 'src.main'
```

## Environment variables (.env)

Required in `.env` (gitignored):
- `TELEGRAM_BOT_TOKEN` — Bot token from @BotFather
- `TELEGRAM_CHAT_ID` — Authorized chat ID (integer)
- `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_ACCESS_TOKEN`
- `FB_AD_ACCOUNT_IDS` — Comma-separated, each prefixed with `act_`
- `NOTION_API_KEY` — Notion integration token (for /sync)
- `NOTION_CLIENTS_DB_ID` — Notion database ID for clients

Optional:
- `TIMEZONE` (default: `Europe/Rome`)
- `REPORT_TIME_HOUR` (default: `9`)

## State file

Client/offer data synced from Notion is cached at:
```
~/.claude/skills/medspa-ads/state.json
```
This file is outside the repo (not committed). It persists between sessions and is shared with the medspa-ads Claude Code skill.

## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu with inline buttons |
| `/report` | Yesterday's metrics per ad account |
| `/weekly` | 7-day comparison report |
| `/campaigns` | Browse & manage campaigns/adsets/ads |
| `/generate_ads` | Generate ad images for a med-spa client |
| `/sync` | Refresh client list from Notion |
| `/help` | List available commands |

## Notion integration

The bot syncs client data from a Notion database using `notion-client`. The sync fetches all pages from the Clients DB via `databases.query()`, extracts client name, stage, and intro offers, then caches them in `state.json`. The `/sync` command triggers this manually; data is also available to the medspa-ads skill for ad generation.

## Related skill

The `medspa-ads` skill at `~/.claude/skills/medspa-ads/SKILL.md` handles AI-powered ad image and copy generation. It reads the same `state.json` for client/offer data.
