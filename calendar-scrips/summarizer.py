"""
Summarization (SPEC §8).

Produces a deterministic, factual report (always) and an optional AI-rewritten
narrative (when an LLM key is configured). The factual text is the canonical
artifact and the fallback: any LLM failure or empty output degrades gracefully
to it, so an AI problem never blocks delivery.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

from models import Event
from timewindow import days_in_window

# --- Localization -----------------------------------------------------------
# The deterministic text is kept in the report language (default Spanish, SPEC
# §4). Day/month names are hard-coded rather than via strftime so output is
# stable regardless of the Pi's locale.
_ES = {
    "weekdays": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
    "months": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    "all_day": "todo el día",
    "free": "— libre —",
    "header": "📅 Agenda · semana del {a} al {b}",
    "header_past": "📅 Resumen · semana del {a} al {b}",
    "total_events": "Total de eventos",
    "scheduled_time": "Tiempo agendado",
    "no_events": "Sin eventos esta semana.",
}
_EN = {
    "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "all_day": "all day",
    "free": "— free —",
    "header": "📅 Agenda · week of {a} to {b}",
    "header_past": "📅 Recap · week of {a} to {b}",
    "total_events": "Total events",
    "scheduled_time": "Scheduled time",
    "no_events": "No events this week.",
}


def _labels(language: str) -> dict:
    norm = (language or "").strip().lower()
    if norm.startswith(("en", "ing")):  # English / Inglés
        return _EN
    return _ES  # Spanish default (SPEC §4)


# --- Anthropic API (LLM rewrite) --------------------------------------------
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
LLM_MAX_TOKENS = 700  # bound output length — it must fit a notification
LLM_TIMEOUT = 30


@dataclass
class Report:
    header: str  # date-range line; also used as the email subject (SPEC §9)
    text: str    # full message body delivered to the channels


def _fmt_date(d, labels: dict, with_year: bool = False) -> str:
    s = f"{d.day} {labels['months'][d.month - 1]}"
    return f"{s} {d.year}" if with_year else s


def _build_header(window_start, window_end, scope, labels: dict) -> str:
    start_d = window_start.date()
    end_d = (window_end - timedelta(days=1)).date()  # inclusive last day
    a = _fmt_date(start_d, labels)
    b = _fmt_date(end_d, labels, with_year=True)
    key = "header_past" if scope == "past" else "header"
    return labels[key].format(a=a, b=b)


def _format_event_line(event: Event, labels: dict) -> str:
    if event.all_day:
        return f"{event.title} — {labels['all_day']}"
    start = event.start.strftime("%H:%M")
    end = event.end.strftime("%H:%M")
    return f"{start}–{end}  {event.title}"


def _format_duration(total: timedelta) -> str:
    minutes = int(total.total_seconds() // 60)
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins}min"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def build_factual_report(events, window_start, window_end, scope, language) -> Report:
    """Build the deterministic, factual report (SPEC §8.1).

    Groups events by day across the window, lists each day's events (or marks it
    free), and appends the total event count and total scheduled time (timed
    events only — all-day events are excluded from hour totals).
    """
    labels = _labels(language)
    header = _build_header(window_start, window_end, scope, labels)
    lines = [header, ""]

    if not events:
        lines.append(labels["no_events"])
        lines.append("")

    for day in days_in_window(window_start, window_end):
        weekday = labels["weekdays"][day.weekday()]
        lines.append(f"{weekday} {_fmt_date(day, labels)}")

        day_events = [e for e in events if e.occurs_on(day)]
        if not day_events:
            lines.append(f"   {labels['free']}")
        else:
            for event in day_events:
                lines.append("   " + _format_event_line(event, labels))
        lines.append("")

    total_time = sum((e.duration for e in events), timedelta())
    lines.append(f"{labels['total_events']}: {len(events)}")
    lines.append(f"{labels['scheduled_time']}: {_format_duration(total_time)}")

    return Report(header=header, text="\n".join(lines).rstrip())


def _system_prompt(language: str) -> str:
    return (
        f"You rewrite a factual weekly calendar summary into a short, friendly "
        f"briefing written in {language}. Group the days sensibly, name the "
        f"busiest day, state the total committed hours, and call out any free "
        f"days. Keep it concise — it must fit in a phone notification.\n"
        f"CRITICAL: use ONLY the events present in the input. Never invent, "
        f"merge, infer, or guess events. The factual text is the sole source of "
        f"truth. Output only the briefing — no preamble, sign-off, or questions."
    )


def llm_rewrite(factual_text, *, api_key, model, language) -> str | None:
    """Rewrite the factual text via the Anthropic API.

    Returns the narrative on success, or ``None`` on any error or empty output
    so the caller falls back to the factual text (SPEC §8.2, §10).
    """
    try:
        response = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": LLM_MAX_TOKENS,
                "system": _system_prompt(language),
                "messages": [{"role": "user", "content": factual_text}],
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        blocks = response.json().get("content", [])
        text = "".join(
            b.get("text", "") for b in blocks if b.get("type") == "text"
        ).strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 — any failure must degrade gracefully
        # The exception text does not contain the API key (it is only in a
        # request header), so this is safe to log (SPEC §10, §11).
        print(f"[llm] rewrite failed, falling back to factual text: {exc}")
        return None


def summarize(events, window_start, window_end, cfg) -> Report:
    """Build the final report: factual by default, AI narrative if configured.

    The factual header (date range) is always kept as the report header so the
    email subject and the visible range stay correct even when an LLM rewrites
    the body.
    """
    report = build_factual_report(
        events, window_start, window_end, cfg.report_scope, cfg.report_language
    )
    if cfg.llm_api_key:
        narrative = llm_rewrite(
            report.text,
            api_key=cfg.llm_api_key,
            model=cfg.llm_model,
            language=cfg.report_language,
        )
        if narrative:
            return Report(
                header=report.header,
                text=f"{report.header}\n\n{narrative}",
            )
    return report
