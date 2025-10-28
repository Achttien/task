from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

import pytz
from dateutil import parser as dateutil_parser

from .config import AppConfig


@dataclass
class CalendarEvent:
    id: Optional[str]
    summary: str
    start: dt.datetime
    end: dt.datetime
    all_day: bool
    location: Optional[str]
    description: Optional[str]
    attendees: List[str]
    html_link: Optional[str]


class CalendarManager:
    def __init__(self, cfg: AppConfig, cal_service, tz: str):
        self.cfg = cfg
        self.cal = cal_service
        self.tz = tz
        self.tzinfo = pytz.timezone(tz)

    def get_calendar_timezone(self) -> str:
        cal_meta = self.cal.calendars().get(calendarId=self.cfg.google.calendar_id).execute()
        return cal_meta.get("timeZone", self.tz)

    def list_events_for_range(self, start: dt.datetime, end: dt.datetime) -> List[CalendarEvent]:
        time_min = start.isoformat()
        time_max = end.isoformat()
        events: List[CalendarEvent] = []
        page_token = None
        while True:
            resp = (
                self.cal.events()
                .list(
                    calendarId=self.cfg.google.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )
            for item in resp.get("items", []):
                ev = self._from_api_item(item)
                if ev:
                    events.append(ev)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return events

    def _from_api_item(self, item) -> Optional[CalendarEvent]:
        status = item.get("status")
        if status == "cancelled":
            return None
        summary = item.get("summary", "(No title)")
        html_link = item.get("htmlLink")
        location = item.get("location")
        description = item.get("description")
        attendees = [a.get("email") for a in item.get("attendees", []) if a.get("email")]
        start_raw = item.get("start", {})
        end_raw = item.get("end", {})
        if "date" in start_raw:
            # All-day event
            all_day = True
            start_date = dt.datetime.strptime(start_raw["date"], "%Y-%m-%d").date()
            end_date = dt.datetime.strptime(end_raw["date"], "%Y-%m-%d").date()
            start = self.tzinfo.localize(dt.datetime.combine(start_date, dt.time(0, 0)))
            # Google all-day end is exclusive; subtract 1 minute to represent end of day
            end = self.tzinfo.localize(dt.datetime.combine(end_date, dt.time(0, 0))) - dt.timedelta(minutes=1)
        else:
            all_day = False
            # dateTime fields may include timezone offset or 'Z'. Use dateutil to parse robustly.
            def parse_dt(raw: dict) -> dt.datetime:
                s = raw.get("dateTime")
                d = dateutil_parser.isoparse(s)
                if d.tzinfo is None and raw.get("timeZone"):
                    try:
                        tz = pytz.timezone(raw["timeZone"]) 
                        d = tz.localize(d)
                    except Exception:
                        d = self.tzinfo.localize(d)
                return d

            start = parse_dt(start_raw)
            end = parse_dt(end_raw)
            # Normalize to target tz
            start = start.astimezone(self.tzinfo)
            end = end.astimezone(self.tzinfo)
        return CalendarEvent(
            id=item.get("id"),
            summary=summary,
            start=start,
            end=end,
            all_day=all_day,
            location=location,
            description=description,
            attendees=attendees,
            html_link=html_link,
        )

    def create_or_update_event(self, ev: CalendarEvent) -> CalendarEvent:
        body = self._to_api_body(ev)
        if ev.id:
            item = (
                self.cal.events()
                .patch(calendarId=self.cfg.google.calendar_id, eventId=ev.id, body=body)
                .execute()
            )
        else:
            item = self.cal.events().insert(calendarId=self.cfg.google.calendar_id, body=body).execute()
        updated = self._from_api_item(item)
        # Preserve id/html if needed
        if updated:
            return updated
        # Fallback to raw values if parsing failed (should not happen)
        return ev

    def _to_api_body(self, ev: CalendarEvent) -> dict:
        if ev.all_day:
            # Google expects exclusive end date for all-day
            start_date = ev.start.date()
            end_date_exclusive = ev.end.date() + dt.timedelta(days=1)
            start = {"date": start_date.strftime("%Y-%m-%d")}
            end = {"date": end_date_exclusive.strftime("%Y-%m-%d")}
        else:
            start = {"dateTime": ev.start.astimezone(self.tzinfo).isoformat()}
            end = {"dateTime": ev.end.astimezone(self.tzinfo).isoformat()}
        body = {
            "summary": ev.summary,
            "start": start,
            "end": end,
        }
        if ev.location:
            body["location"] = ev.location
        if ev.description:
            body["description"] = ev.description
        if ev.attendees:
            body["attendees"] = [{"email": a} for a in ev.attendees]
        return body

    def parse_row_to_event(
        self,
        title: str,
        start_str: str,
        end_str: str,
        all_day_str: str,
        location: Optional[str],
        description: Optional[str],
        attendees_str: Optional[str],
    ) -> CalendarEvent:
        all_day = str(all_day_str).strip().lower() in ("1", "true", "yes", "y")
        if all_day:
            start_date = dt.datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
            end_date = dt.datetime.strptime(end_str.strip(), "%Y-%m-%d").date()
            start_dt = self.tzinfo.localize(dt.datetime.combine(start_date, dt.time(0, 0)))
            end_dt = self.tzinfo.localize(dt.datetime.combine(end_date, dt.time(23, 59)))
        else:
            # "YYYY-MM-DD HH:MM" or ISO
            def parse_dt(s: str) -> dt.datetime:
                s = s.strip()
                try:
                    # try human-friendly format first
                    naive = dt.datetime.strptime(s, "%Y-%m-%d %H:%M")
                    return self.tzinfo.localize(naive)
                except Exception:
                    # fallback to fromisoformat with timezone
                    d = dt.datetime.fromisoformat(s)
                    return d.astimezone(self.tzinfo)

            start_dt = parse_dt(start_str)
            end_dt = parse_dt(end_str)
        attendees = []
        if attendees_str:
            attendees = [x.strip() for x in attendees_str.split(",") if x.strip()]
        return CalendarEvent(
            id=None,
            summary=title.strip() or "(No title)",
            start=start_dt,
            end=end_dt,
            all_day=all_day,
            location=(location or "").strip() or None,
            description=(description or "").strip() or None,
            attendees=attendees,
            html_link=None,
        )
