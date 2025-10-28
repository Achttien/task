from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict

from .config import DEFAULT_STATE_DIR

STATE_PATH = os.path.join(DEFAULT_STATE_DIR, "state.json")


@dataclass
class WeekState:
    week_title: str
    slack_posts_by_event: Dict[str, str] = field(default_factory=dict)  # event_key -> slack ts


@dataclass
class AppState:
    weeks: Dict[str, WeekState] = field(default_factory=dict)  # week_title -> WeekState


def load_state(path: str = STATE_PATH) -> AppState:
    if not os.path.exists(path):
        return AppState()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        weeks = {}
        for k, v in raw.get("weeks", {}).items():
            weeks[k] = WeekState(week_title=v.get("week_title", k), slack_posts_by_event=v.get("slack_posts_by_event", {}))
        return AppState(weeks=weeks)
    except Exception:
        return AppState()


essure_dir = os.makedirs  # alias


def save_state(state: AppState, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"weeks": {k: asdict(v) for k, v in state.weeks.items()}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
