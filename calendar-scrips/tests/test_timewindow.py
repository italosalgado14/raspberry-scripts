"""Week-boundary computation, incl. the Monday edge case and DST (SPEC §13)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from timewindow import compute_window, days_in_window

TZ = ZoneInfo("America/Santiago")


def _dt(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=TZ)


def test_upcoming_from_midweek():
    # Wednesday 2026-06-10 -> next Monday 2026-06-15 .. 2026-06-22.
    start, end = compute_window(_dt(2026, 6, 10), "upcoming", TZ)
    assert start.date().isoformat() == "2026-06-15"
    assert end.date().isoformat() == "2026-06-22"
    assert start.weekday() == 0 and end.weekday() == 0


def test_upcoming_on_monday_starts_today():
    # Monday 2026-06-08 -> window starts today (SPEC §6 edge case).
    start, end = compute_window(_dt(2026, 6, 8), "upcoming", TZ)
    assert start.date().isoformat() == "2026-06-08"
    assert end.date().isoformat() == "2026-06-15"


def test_upcoming_on_sunday_starts_tomorrow():
    # Sunday 2026-06-07 -> next Monday 2026-06-08 (Sunday-evening cadence).
    start, _ = compute_window(_dt(2026, 6, 7), "upcoming", TZ)
    assert start.date().isoformat() == "2026-06-08"


def test_past_is_previous_completed_week():
    # Wednesday 2026-06-10 -> previous Mon..Sun block = 2026-06-01 .. 2026-06-08.
    start, end = compute_window(_dt(2026, 6, 10), "past", TZ)
    assert start.date().isoformat() == "2026-06-01"
    assert end.date().isoformat() == "2026-06-08"


def test_boundaries_are_local_midnight():
    start, end = compute_window(_dt(2026, 6, 10), "upcoming", TZ)
    assert (start.hour, start.minute, start.second) == (0, 0, 0)
    assert (end.hour, end.minute, end.second) == (0, 0, 0)
    assert start.tzinfo is not None


def test_window_spans_seven_days_across_dst():
    # Chile's spring-forward transition is in September; a window straddling it
    # must still be exactly 7 calendar days with both boundaries at midnight.
    start, end = compute_window(_dt(2026, 9, 9), "past", TZ)
    days = days_in_window(start, end)
    assert len(days) == 7
    assert start.hour == 0 and end.hour == 0


def test_unknown_scope_raises():
    with pytest.raises(ValueError):
        compute_window(_dt(2026, 6, 10), "sideways", TZ)
