"""Deterministic summary: grouping, free days, duration aggregation (SPEC §13)."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from models import Event
from summarizer import _format_duration, build_factual_report

TZ = ZoneInfo("America/Santiago")


def _window():
    start = datetime(2026, 6, 15, 0, 0, tzinfo=TZ)
    end = datetime(2026, 6, 22, 0, 0, tzinfo=TZ)
    return start, end


def _timed(title, day, h1, m1, h2, m2):
    return Event(
        title,
        False,
        datetime(2026, 6, day, h1, m1, tzinfo=TZ),
        datetime(2026, 6, day, h2, m2, tzinfo=TZ),
    )


def test_counts_and_hours_exclude_all_day():
    start, end = _window()
    events = [
        _timed("Standup", 15, 9, 0, 9, 30),  # 30 min
        _timed("Gym", 16, 18, 0, 19, 30),    # 90 min
        Event("Feriado", True, date(2026, 6, 17), date(2026, 6, 18)),  # all-day
    ]
    report = build_factual_report(events, start, end, "upcoming", "Spanish")
    assert "Total de eventos: 3" in report.text
    assert "2h" in report.text          # 30 + 90 min == 2h, all-day excluded
    assert "todo el día" in report.text


def test_empty_week_marks_days_free():
    start, end = _window()
    report = build_factual_report([], start, end, "upcoming", "Spanish")
    assert "libre" in report.text
    assert "Total de eventos: 0" in report.text
    assert "Sin eventos" in report.text


def test_english_labels():
    start, end = _window()
    report = build_factual_report([], start, end, "upcoming", "English")
    assert "free" in report.text
    assert "Total events: 0" in report.text


def test_format_duration():
    assert _format_duration(timedelta(minutes=30)) == "30min"
    assert _format_duration(timedelta(hours=2)) == "2h"
    assert _format_duration(timedelta(hours=2, minutes=15)) == "2h 15min"


def test_header_is_subject_and_prefixes_body():
    start, end = _window()
    report = build_factual_report([], start, end, "upcoming", "Spanish")
    assert report.header
    assert report.text.startswith(report.header)
