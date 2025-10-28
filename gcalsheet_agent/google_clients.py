from __future__ import annotations

import json
import os
from typing import Tuple, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from .config import AppConfig

CAL_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _load_credentials(token_path: str) -> Optional[Credentials]:
    if os.path.exists(token_path):
        try:
            return Credentials.from_authorized_user_file(token_path)
        except Exception:
            return None
    return None


def _save_credentials(creds: Credentials, token_path: str) -> None:
    with open(token_path, "w", encoding="utf-8") as token:
        token.write(creds.to_json())


def authenticate_google(cfg: AppConfig) -> Tuple[object, object]:
    token_path = cfg.google.token_path
    client_secret = cfg.google.credentials_path

    cal_creds = _load_credentials(token_path)
    sheets_creds = None

    if cal_creds and cal_creds.expired and cal_creds.refresh_token:
        cal_creds.refresh(Request())

    if not cal_creds or not cal_creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret, scopes=list(set(CAL_SCOPES + SHEETS_SCOPES)))
        cal_creds = flow.run_local_server(port=0)
        _save_credentials(cal_creds, token_path)

    # reuse same creds for sheets
    sheets_creds = cal_creds

    cal_service = build("calendar", "v3", credentials=cal_creds, cache_discovery=False)
    sheets_service = build("sheets", "v4", credentials=sheets_creds, cache_discovery=False)
    drive_service = build("drive", "v3", credentials=sheets_creds, cache_discovery=False)

    return (cal_service, sheets_service, drive_service)
