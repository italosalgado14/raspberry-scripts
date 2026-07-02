#!/usr/bin/env python3
"""
Weekly Calendar Report — runner (SPEC §2, §10).

Stateless orchestrator: read config → compute the week window → fetch Google
Calendar events → summarize (optionally via an LLM) → dispatch to every active
channel. Designed to run unattended from cron on a Raspberry Pi, and identically
on demand for testing.

    uv run calendar_report.py            # full run: fetch, summarize, deliver
    uv run calendar_report.py --dry-run  # fetch + print summary, do NOT deliver
    uv run calendar_report.py --raw      # print the raw Google API events (JSON)

The --dry-run and --raw modes need only the calendar credentials — no Telegram
or email configuration — so they are the easiest way to test the Google side
first.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from calendar_reader import build_service, fetch_events, fetch_raw_events
from dispatcher import dispatch
from summarizer import summarize
from timewindow import compute_window


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Weekly Google Calendar report (Telegram / email)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print the formatted summary but do NOT deliver it "
        "(no Telegram/email config required).",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the raw Google Calendar API events as JSON, then exit "
        "(no delivery config required).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)

    cfg = config.load_config()
    config.validate_calendar(cfg)  # always need read access to the calendar
    # For a real delivering run, fail loud on channel misconfig before any work.
    if not args.dry_run and not args.raw:
        config.validate_channels(cfg)

    tz = ZoneInfo(cfg.calendar_tz)
    now = datetime.now(tz)
    window_start, window_end = compute_window(now, cfg.report_scope, tz)

    service = build_service(cfg.calendar_credentials)

    if args.raw:
        # Show exactly what Google returns (after recurring expansion).
        raw = fetch_raw_events(
            service, cfg.calendar_id, window_start, window_end, tz
        )
        print(json.dumps(raw, indent=2, ensure_ascii=False))
        return

    events = fetch_events(service, cfg.calendar_id, window_start, window_end, tz)
    report = summarize(events, window_start, window_end, cfg)

    # Print the generated summary so the run log is self-explanatory (§10).
    print(report.text)

    if args.dry_run:
        print("\n--- dry-run: delivery skipped ---")
        return

    print("---")
    dispatch(report, cfg)


if __name__ == "__main__":
    main()
