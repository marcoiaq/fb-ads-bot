from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val or val.startswith("your-"):
        print(f"ERROR: environment variable {name} is not set. Check your .env file.")
        sys.exit(1)
    return val


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int
    facebook_app_id: str
    facebook_app_secret: str
    facebook_access_token: str
    ad_account_ids: list[str] = field(default_factory=list)
    timezone: str = "Europe/Rome"
    report_time_hour: int = 9
    notion_api_key: str = ""
    notion_clients_db_id: str = ""

    @classmethod
    def load(cls) -> Settings:
        raw_accounts = _require("FB_AD_ACCOUNT_IDS")
        accounts = [a.strip() for a in raw_accounts.split(",") if a.strip()]
        for acct in accounts:
            if not acct.startswith("act_"):
                print(f"ERROR: ad account ID '{acct}' must start with 'act_'")
                sys.exit(1)

        return cls(
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=int(_require("TELEGRAM_CHAT_ID")),
            facebook_app_id=_require("FACEBOOK_APP_ID"),
            facebook_app_secret=_require("FACEBOOK_APP_SECRET"),
            facebook_access_token=_require("FACEBOOK_ACCESS_TOKEN"),
            ad_account_ids=accounts,
            timezone=os.getenv("TIMEZONE", "Europe/Rome").strip(),
            report_time_hour=int(os.getenv("REPORT_TIME_HOUR", "9")),
            notion_api_key=os.getenv("NOTION_API_KEY", "").strip(),
            notion_clients_db_id=os.getenv("NOTION_CLIENTS_DB_ID", "").strip(),
        )
