from __future__ import annotations

import datetime as dt
from typing import List, Optional, Tuple

import pytz

from .config import AppConfig
from .calendar_manager import CalendarManager, CalendarEvent
from .sheets_manager import SheetsManager, SheetInfo
from .slack_manager import SlackManager
from .state import load_state, save_state, AppState, WeekState


SHEET_HEADER = [
    "Event ID",
    "Title",
    "Start",
    "End",
    "All Day",
    "Location",
    "Description",
    "Attendees (comma emails)",
    "Calendar Link",
]


class SyncEngine:
    def __init__(self, cfg: AppConfig, cal_service, sheets_service, drive_service, tz: str):
        self.cfg = cfg
        self.calendar = CalendarManager(cfg, cal_service, tz)
        self.sheets = SheetsManager(cfg, sheets_service, drive_service, tz)
        self.slack = SlackManager(cfg)
        self.tz = tz
        self.tzinfo = pytz.timezone(tz)

    def sync_week(self, now: Optional[dt.date] = None) -> Tuple[SheetInfo, List[CalendarEvent]]:
        sheet_info = self.sheets.get_or_create_week_sheet(now=now)
        ws, we = self.sheets.get_week_range(now=now)
        start_dt = self.tzinfo.localize(dt.datetime.combine(ws, dt.time(0, 0)))
        end_dt = self.tzinfo.localize(dt.datetime.combine(we, dt.time(23, 59)))
        events = self.calendar.list_events_for_range(start_dt, end_dt)

        # Write to sheet
        self.sheets.write_header_if_empty(sheet_info, SHEET_HEADER)
        self.sheets.upsert_events(sheet_info, events)

        # Slack one-way: add to todo list
        if self.cfg.sync.slack_one_way:
            self._post_slack_todos(events)

        return sheet_info, events

    def sheet_to_calendar_updates(self, sheet_info: SheetInfo) -> List[tuple[int, CalendarEvent]]:
        if not self.cfg.sync.two_way:
            return []
        rows = self.sheets.read_rows(sheet_info)
        updates: List[tuple[int, CalendarEvent]] = []
        for rownum, row in enumerate(rows, start=2):
            # Expect same order as SHEET_HEADER
            event_id, title, start, end, all_day, location, description, attendees, _ = (
                row + [None] * 9
            )[:9]
            if not title or not start or not end:
                continue
            ev = self.calendar.parse_row_to_event(
                title=title,
                start_str=start,
                end_str=end,
                all_day_str=str(all_day or ""),
                location=location,
                description=description,
                attendees_str=attendees,
            )
            ev.id = (event_id or "").strip() or None
            updates.append((rownum, ev))
        return updates

    def apply_updates_to_calendar(self, sheet_info: SheetInfo, row_events: List[tuple[int, CalendarEvent]]) -> List[CalendarEvent]:
        updated: List[CalendarEvent] = []
        for rownum, ev in row_events:
            new_ev = self.calendar.create_or_update_event(ev)
            updated.append(new_ev)
            # Write back event with ID and link to the same row
            self.sheets.update_row_from_event(sheet_info=sheet_info, rownum=rownum, event=new_ev)
        return updated

    def _post_slack_todos(self, events: List[CalendarEvent]) -> None:
        if not events:
            return
        # Persist posts per week to avoid duplicates
        sheet_info = self.sheets.get_or_create_week_sheet()
        week_title = sheet_info.title
        state = load_state()
        week_state = state.weeks.get(week_title) or WeekState(week_title=week_title)

        changed = False
        for ev in events:
            # Use event.id if present, else a composite key
            key = ev.id or f"{ev.summary}|{ev.start.isoformat()}|{ev.end.isoformat()}"
            if week_state.slack_posts_by_event.get(key):
                continue
            title = ev.summary
            if ev.all_day:
                time_str = f"{ev.start:%Y-%m-%d} (all day)"
            else:
                time_str = f"{ev.start:%Y-%m-%d %H:%M} - {ev.end:%H:%M}"
            text = f"📅 {title} — {time_str}"
            ts = self.slack.post_todo(text)
            if ts:
                week_state.slack_posts_by_event[key] = ts
                changed = True

        if changed:
            state.weeks[week_title] = week_state
            save_state(state)
