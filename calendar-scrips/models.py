"""
Shared data model for normalized calendar events.

Kept dependency-free (no Google libraries) so the summarizer and the unit tests
can import it without pulling in the Calendar API client.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class Event:
    """A normalized calendar event (SPEC §7).

    For *timed* events, ``start``/``end`` are timezone-aware ``datetime`` objects
    already converted to the report timezone. For *all-day* events they are
    ``date`` objects and ``end`` is exclusive (Google's convention).
    """

    title: str
    all_day: bool
    start: datetime | date
    end: datetime | date

    @property
    def duration(self) -> timedelta:
        """Scheduled duration. Always zero for all-day events (SPEC §7, §8)."""
        if self.all_day:
            return timedelta(0)
        return self.end - self.start

    def occurs_on(self, day: date) -> bool:
        """Whether this event should be listed under ``day``.

        Timed events are bucketed under their start date. All-day events span
        every date in ``[start, end)`` (end exclusive), so a multi-day all-day
        event (e.g. a holiday block) correctly appears on each day it covers.
        """
        if self.all_day:
            return self.start <= day < self.end
        return self.start.date() == day
