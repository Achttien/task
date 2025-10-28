from __future__ import annotations

from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .config import AppConfig


class SlackManager:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.client = WebClient(token=self.cfg.slack.bot_token) if self.cfg.slack.bot_token else None

    def post_todo(self, text: str) -> Optional[str]:
        if not self.client or not self.cfg.slack.todo_channel:
            return None
        try:
            resp = self.client.chat_postMessage(channel=self.cfg.slack.todo_channel, text=text)
            return resp.get("ts")
        except SlackApiError:
            return None
