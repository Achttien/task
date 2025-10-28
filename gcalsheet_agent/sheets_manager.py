from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict

import pytz

from .config import AppConfig


@dataclass
class SheetInfo:
    spreadsheet_id: str
    sheet_id: int
    title: str


def _iso_week_range(date: dt.date, week_start: int) -> Tuple[dt.date, dt.date]:
    # week_start: 0 = Monday
    delta = (date.weekday() - week_start) % 7
    start = date - dt.timedelta(days=delta)
    end = start + dt.timedelta(days=6)
    return start, end


def _format_week_title(start: dt.date, end: dt.date, pattern: str) -> str:
    # e.g., "Oct 27 - Oct 31"
    return pattern.format(start=start, end=end)


class SheetsManager:
    def __init__(self, cfg: AppConfig, sheets_service, drive_service, tz: str):
        self.cfg = cfg
        self.sheets = sheets_service
        self.drive = drive_service
        self.tz = tz

    def ensure_spreadsheet(self) -> str:
        if self.cfg.google.spreadsheet_id:
            return self.cfg.google.spreadsheet_id
        body = {"properties": {"title": self.cfg.google.spreadsheet_title}}
        resp = self.sheets.spreadsheets().create(body=body, fields="spreadsheetId").execute()
        spreadsheet_id = resp["spreadsheetId"]
        # Share to the user only; Drive API requires users to open it for full scope sharing; we keep private
        self.cfg.google.spreadsheet_id = spreadsheet_id
        return spreadsheet_id

    def get_or_create_week_sheet(self, now: Optional[dt.date] = None) -> SheetInfo:
        spreadsheet_id = self.ensure_spreadsheet()
        now = now or dt.datetime.now(pytz.timezone(self.tz)).date()
        ws, we_full = _iso_week_range(now, self.cfg.sync.week_start)
        # Show only span days for title (e.g., Mon-Fri)
        span_end = ws + dt.timedelta(days=self.cfg.sync.week_span_days)
        title = _format_week_title(ws, span_end, self.cfg.sync.sheet_name_format)
        
        meta = self.sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = meta.get("sheets", [])
        for s in sheets:
            if s["properties"]["title"] == title:
                return SheetInfo(
                    spreadsheet_id=spreadsheet_id,
                    sheet_id=s["properties"]["sheetId"],
                    title=title,
                )

        # Create a new sheet for this week
        add_sheet_req = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "gridProperties": {"rowCount": 1000, "columnCount": 9},
                            "tabColor": {"red": 0.85, "green": 0.94, "blue": 1.0},
                        }
                    }
                }
            ]
        }
        resp = self.sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=add_sheet_req
        ).execute()
        sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
        return SheetInfo(spreadsheet_id=spreadsheet_id, sheet_id=sheet_id, title=title)

    def get_week_range(self, now: Optional[dt.date] = None) -> Tuple[dt.date, dt.date]:
        now = now or dt.datetime.now(pytz.timezone(self.tz)).date()
        return _iso_week_range(now, self.cfg.sync.week_start)

    def write_header_if_empty(self, sheet: SheetInfo, header: List[str]) -> None:
        # Read first row
        range_a1 = f"{sheet.title}!A1:{chr(ord('A') + len(header) - 1)}1"
        resp = (
            self.sheets.spreadsheets()
            .values()
            .get(spreadsheetId=sheet.spreadsheet_id, range=range_a1)
            .execute()
        )
        values = resp.get("values", [])
        if values and any(values[0]):
            return
        # Write header and freeze
        self.sheets.spreadsheets().values().update(
            spreadsheetId=sheet.spreadsheet_id,
            range=range_a1,
            valueInputOption="RAW",
            body={"values": [header]},
        ).execute()
        # Freeze the top row and bold header
        batch = {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": sheet.sheet_id, "gridProperties": {"frozenRowCount": 1}},
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet.sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(header),
                        },
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold",
                    }
                },
                {
                    "autoResizeDimensions": {
                        "dimensions": {"sheetId": sheet.sheet_id, "dimension": "COLUMNS", "startIndex": 0}
                    }
                },
            ]
        }
        self.sheets.spreadsheets().batchUpdate(
            spreadsheetId=sheet.spreadsheet_id, body=batch
        ).execute()

    def _read_existing_rows(self, sheet: SheetInfo, num_cols: int) -> List[List[str]]:
        range_a1 = f"{sheet.title}!A2:{chr(ord('A') + num_cols - 1)}"
        resp = (
            self.sheets.spreadsheets()
            .values()
            .get(spreadsheetId=sheet.spreadsheet_id, range=range_a1)
            .execute()
        )
        return resp.get("values", [])

    def read_rows(self, sheet: SheetInfo) -> List[List[str]]:
        # Default to 9 columns as defined by SHEET_HEADER
        return self._read_existing_rows(sheet, num_cols=9)

    def upsert_events(self, sheet: SheetInfo, events: List) -> None:
        # Expect events to be CalendarEvent instances
        num_cols = 9
        existing = self._read_existing_rows(sheet, num_cols=num_cols)
        # Build map from event_id -> row index (starting at 2 for A1 notation)
        id_to_rownum: Dict[str, int] = {}
        for idx, row in enumerate(existing, start=2):
            if row and len(row) > 0 and row[0]:
                id_to_rownum[str(row[0])] = idx

        # Prepare batch updates and appends
        updates = []
        appends = []

        for ev in events:
            if ev.all_day:
                start_str = f"{ev.start:%Y-%m-%d}"
                end_str = f"{ev.end:%Y-%m-%d}"
                all_day = "TRUE"
            else:
                start_str = f"{ev.start:%Y-%m-%d %H:%M}"
                end_str = f"{ev.end:%Y-%m-%d %H:%M}"
                all_day = "FALSE"
            attendees = ", ".join(ev.attendees) if ev.attendees else ""
            row_values = [
                ev.id or "",
                ev.summary or "",
                start_str,
                end_str,
                all_day,
                ev.location or "",
                ev.description or "",
                attendees,
                ev.html_link or "",
            ]
            if ev.id and ev.id in id_to_rownum:
                rownum = id_to_rownum[ev.id]
                range_a1 = f"{sheet.title}!A{rownum}:{chr(ord('A') + num_cols - 1)}{rownum}"
                updates.append({
                    "range": range_a1,
                    "values": [row_values],
                })
            else:
                appends.append(row_values)

        data = []
        if updates:
            data.extend(updates)
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet.spreadsheet_id,
                body={
                    "valueInputOption": "RAW",
                    "data": data,
                },
            ).execute()
        if appends:
            range_a1 = f"{sheet.title}!A1"
            self.sheets.spreadsheets().values().append(
                spreadsheetId=sheet.spreadsheet_id,
                range=range_a1,
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": appends},
            ).execute()

    def update_row_from_event(self, sheet_info: SheetInfo, rownum: int, event) -> None:
        # Update a single row with authoritative values from the Calendar event
        if event.all_day:
            start_str = f"{event.start:%Y-%m-%d}"
            end_str = f"{event.end:%Y-%m-%d}"
            all_day = "TRUE"
        else:
            start_str = f"{event.start:%Y-%m-%d %H:%M}"
            end_str = f"{event.end:%Y-%m-%d %H:%M}"
            all_day = "FALSE"
        attendees = ", ".join(event.attendees) if getattr(event, "attendees", None) else ""
        row_values = [
            event.id or "",
            event.summary or "",
            start_str,
            end_str,
            all_day,
            event.location or "",
            event.description or "",
            attendees,
            event.html_link or "",
        ]
        num_cols = len(row_values)
        range_a1 = f"{sheet_info.title}!A{rownum}:{chr(ord('A') + num_cols - 1)}{rownum}"
        self.sheets.spreadsheets().values().update(
            spreadsheetId=sheet_info.spreadsheet_id,
            range=range_a1,
            valueInputOption="RAW",
            body={"values": [row_values]},
        ).execute()