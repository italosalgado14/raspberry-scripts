"""
Week-window computation (SPEC §6).

Pure date logic, no I/O, so it is straightforward to unit-test across the
Monday edge case and DST transitions. All boundaries are computed at local
midnight in the target timezone and returned as timezone-aware datetimes
forming the half-open interval ``[start, end)`` — a Monday→Monday week.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

UPCOMING = "upcoming"
PAST = "past"


def _as_tz(tz) -> ZoneInfo:
    return tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)


def _midnight(day: date, tz: ZoneInfo) -> datetime:
    """Local midnight of ``day`` in ``tz`` (offset resolved by zoneinfo)."""
    return datetime.combine(day, time.min, tzinfo=tz)


def compute_window(now: datetime, scope: str, tz) -> tuple[datetime, datetime]:
    """Return the ``(start, end)`` datetimes for the report window.

    ``now`` should be timezone-aware. ``scope`` is ``"upcoming"`` or ``"past"``.
    The interval is half-open: ``[start, end)``.

    * **upcoming** — next Monday 00:00 (inclusive) → following Monday 00:00
      (exclusive). If today is Monday, the window starts today.
    * **past** — the most recently completed Monday–Sunday block.
    """
    tz = _as_tz(tz)
    today = now.astimezone(tz).date()
    weekday = today.weekday()  # Monday == 0 ... Sunday == 6

    if scope == UPCOMING:
        days_until_monday = (7 - weekday) % 7  # 0 when today is Monday
        start_day = today + timedelta(days=days_until_monday)
    elif scope == PAST:
        this_monday = today - timedelta(days=weekday)
        start_day = this_monday - timedelta(days=7)
    else:
        raise ValueError(
            f"unknown scope {scope!r}; expected 'upcoming' or 'past'"
        )

    end_day = start_day + timedelta(days=7)
    return _midnight(start_day, tz), _midnight(end_day, tz)


def days_in_window(start: datetime, end: datetime) -> list[date]:
    """The calendar dates from ``start`` (inclusive) to ``end`` (exclusive)."""
    days = []
    day = start.date()
    last = end.date()
    while day < last:
        days.append(day)
        day += timedelta(days=1)
    return days
