from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

DEFAULT_STATE_DIR = os.path.join(os.getcwd(), ".gcalsheet-agent")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_STATE_DIR, "config.json")


@dataclass
class SlackConfig:
    bot_token: Optional[str] = None
    todo_channel: Optional[str] = None  # channel ID or name for posting todos


@dataclass
class GoogleConfig:
    credentials_path: str = os.path.join(DEFAULT_STATE_DIR, "client_secret.json")
    token_path: str = os.path.join(DEFAULT_STATE_DIR, "token.json")
    calendar_id: str = "primary"
    spreadsheet_id: Optional[str] = None  # if None, will create on first run
    spreadsheet_title: str = "Calendar Weekly Sync"
    timezone: Optional[str] = None  # If None, auto-detect from Calendar settings


@dataclass
class SyncConfig:
    two_way: bool = True  # enable 2-way sync
    week_start: int = 0  # 0=Monday, per ISO
    # span of days from week start to display in sheet name; default Mon->Fri (4 days after start)
    week_span_days: int = 4
    sheet_name_format: str = "{start:%b %d} - {end:%b %d}"
    slack_one_way: bool = True
    include_attendees: bool = False


@dataclass
class AppConfig:
    google: GoogleConfig
    slack: SlackConfig
    sync: SyncConfig

    @staticmethod
    def default() -> "AppConfig":
        return AppConfig(google=GoogleConfig(), slack=SlackConfig(), sync=SyncConfig())


def ensure_state_dir(path: str = DEFAULT_STATE_DIR) -> None:
    os.makedirs(path, exist_ok=True)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
    ensure_state_dir(os.path.dirname(path))
    if not os.path.exists(path):
        cfg = AppConfig.default()
        save_config(cfg, path)
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return AppConfig(
        google=GoogleConfig(**raw.get("google", {})),
        slack=SlackConfig(**raw.get("slack", {})),
        sync=SyncConfig(**raw.get("sync", {})),
    )


def save_config(cfg: AppConfig, path: str = DEFAULT_CONFIG_PATH) -> None:
    ensure_state_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2)
