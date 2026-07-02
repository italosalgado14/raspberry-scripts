"""
Google Calendar reading (SPEC §5, §7).

Authenticates with a read-only service account, fetches every event in the
window (expanding recurring events into instances, paginating, excluding
cancelled ones), and normalizes them into `Event` objects so the rest of the
program never has to know the Google API shape.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from models import Event

# Least-privilege: read-only Calendar scope only (SPEC §5).
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Google's per-page maximum for events.list().
PAGE_SIZE = 250


def _load_credentials_info(credentials: str) -> dict:
    """Accept either a path to the JSON key file or the inline JSON string.

    On a Pi the credential is usually a file on disk; in a CI runner it is
    typically an injected secret holding the JSON itself. Supporting both keeps
    the same code working in either place.
    """
    if os.path.exists(credentials):
        with open(credentials, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(credentials)


def build_service(credentials: str):
    """Build an authenticated, read-only Calendar API service."""
    info = _load_credentials_info(credentials)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )
    # cache_discovery=False avoids a noisy warning and a needless on-disk cache.
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_dt(value: str, tz: ZoneInfo) -> datetime:
    """Parse an RFC3339 datetime and convert it to ``tz`` (SPEC §7)."""
    # Google returns e.g. "2026-06-09T14:00:00-04:00" or "...Z".
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(tz)


def parse_event(raw: dict, tz: ZoneInfo) -> Event | None:
    """Normalize one raw API event. Returns ``None`` if cancelled (SPEC §7)."""
    if raw.get("status") == "cancelled":
        return None

    title = (raw.get("summary") or "(sin título)").strip()
    start = raw.get("start", {})
    end = raw.get("end", {})

    if "date" in start:  # all-day event (date-only start/end)
        return Event(
            title=title,
            all_day=True,
            start=date.fromisoformat(start["date"]),
            end=date.fromisoformat(end["date"]),
        )

    return Event(
        title=title,
        all_day=False,
        start=_parse_dt(start["dateTime"], tz),
        end=_parse_dt(end["dateTime"], tz),
    )


def fetch_raw_events(service, calendar_id, window_start, window_end, tz) -> list[dict]:
    """Fetch the raw API event dicts in ``[window_start, window_end)``.

    Expands recurring events (``singleEvents=True``), orders by start time,
    excludes deleted events, and paginates until exhausted (SPEC §7). Raises on
    API/network failure so the scheduler's run log captures it (SPEC §10).

    Returned untouched so callers (e.g. ``--raw``) can inspect exactly what
    Google sends back.
    """
    items: list[dict] = []
    page_token = None
    while True:
        response = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=window_start.isoformat(),
                timeMax=window_end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                showDeleted=False,
                maxResults=PAGE_SIZE,
                timeZone=str(tz),
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return items


def fetch_events(service, calendar_id, window_start, window_end, tz) -> list[Event]:
    """Fetch and normalize all events in ``[window_start, window_end)``.

    Builds on :func:`fetch_raw_events`; cancelled events are dropped during
    normalization (SPEC §7).
    """
    events: list[Event] = []
    for raw in fetch_raw_events(service, calendar_id, window_start, window_end, tz):
        event = parse_event(raw, tz)
        if event is not None:
            events.append(event)
    return events
