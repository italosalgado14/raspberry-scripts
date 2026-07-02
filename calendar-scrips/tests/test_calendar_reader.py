"""Event parsing: timed vs all-day, tz conversion, duration, cancelled (SPEC §13)."""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from calendar_reader import parse_event

TZ = ZoneInfo("America/Santiago")


def test_parse_timed_event_converts_tz_and_duration():
    raw = {
        "status": "confirmed",
        "summary": "Standup",
        "start": {"dateTime": "2026-06-15T09:00:00-04:00"},
        "end": {"dateTime": "2026-06-15T09:30:00-04:00"},
    }
    e = parse_event(raw, TZ)
    assert e.all_day is False
    assert e.title == "Standup"
    assert e.duration == timedelta(minutes=30)
    assert e.occurs_on(date(2026, 6, 15))
    assert not e.occurs_on(date(2026, 6, 16))


def test_parse_all_day_event_zero_duration_and_span():
    raw = {
        "status": "confirmed",
        "summary": "Vacaciones",
        "start": {"date": "2026-06-15"},
        "end": {"date": "2026-06-18"},  # end is exclusive
    }
    e = parse_event(raw, TZ)
    assert e.all_day is True
    assert e.duration == timedelta(0)
    assert e.occurs_on(date(2026, 6, 15))
    assert e.occurs_on(date(2026, 6, 17))  # multi-day spans each covered date
    assert not e.occurs_on(date(2026, 6, 18))  # end exclusive


def test_parse_utc_datetime_converts_to_local():
    raw = {
        "status": "confirmed",
        "summary": "UTC mtg",
        "start": {"dateTime": "2026-06-15T12:00:00Z"},
        "end": {"dateTime": "2026-06-15T13:00:00Z"},
    }
    e = parse_event(raw, TZ)
    # 12:00 UTC -> 08:00 in America/Santiago (UTC-4 in June, no DST).
    assert e.start.hour == 8


def test_cancelled_event_is_dropped():
    raw = {
        "status": "cancelled",
        "start": {"date": "2026-06-15"},
        "end": {"date": "2026-06-16"},
    }
    assert parse_event(raw, TZ) is None


def test_missing_summary_gets_placeholder():
    raw = {
        "status": "confirmed",
        "start": {"dateTime": "2026-06-15T09:00:00-04:00"},
        "end": {"dateTime": "2026-06-15T10:00:00-04:00"},
    }
    e = parse_event(raw, TZ)
    assert e.title  # non-empty placeholder, never raises
