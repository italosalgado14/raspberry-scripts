# Technical Specification — Weekly Calendar Report

**Version:** 1.0
**Status:** Draft for implementation
**Author:** —
**Audience:** Implementing engineer

---

## 1. Purpose & Goal

Build an unattended service that, once per week, reads the user's Google
Calendar, produces a human-readable summary of the upcoming week's activities,
and delivers it to the user's phone via Telegram and/or email. The service must
run with no device of the user's awake (fully serverless/scheduled) and at
effectively zero cost.

### Non-goals
- Two-way calendar editing (read-only only).
- Real-time / push-on-change notifications (it is a scheduled batch job).
- A user-facing UI or web app.
- Multi-user / multi-tenant support (single user, single account).

---

## 2. High-Level Architecture

A single scheduled job triggers a stateless runner. The runner authenticates to
Google Calendar, fetches events for a computed time window, transforms them into
a summary (optionally rewritten by an LLM), and dispatches the result over one or
more delivery channels.

```
[Scheduler/cron]
      │ triggers
      ▼
[Runner] ──auth──► [Google Calendar API]  (read events)
      │
      ├─ transform events → factual summary
      ├─ (optional) LLM rewrite → narrative summary
      │
      └─ dispatch ──► [Telegram] and/or [Email/SMTP]
```

### Components
1. **Scheduler** — fires the runner on a weekly cadence; also supports manual
   on-demand invocation.
2. **Runner** — stateless executable; orchestrates the flow; no persistent
   storage required between runs.
3. **Calendar Reader** — authenticates and retrieves events.
4. **Summarizer** — deterministic formatter; optional LLM enhancement.
5. **Dispatcher** — one adapter per delivery channel; channels auto-enable based
   on available configuration.

---

## 3. Execution Environment & Scheduling

- **Trigger:** cron-style schedule, default weekly. Reference cadence: Sunday
  evening local time (preview of the week ahead).
- **Timezone caveat:** if the scheduler runs in UTC, the schedule expression
  must be offset for the user's timezone (default `America/Santiago`, UTC−4 /
  −3 during DST). The cadence is approximate; exact minute is not critical.
- **Manual run:** the system must expose a way to trigger a run on demand for
  testing.
- **Idempotency:** a run has no side effects beyond sending messages; re-running
  simply re-sends. No dedup/state required.
- **Runtime budget:** a single run should complete in well under a minute.

Recommended hosting (any equivalent is acceptable): a free scheduled CI runner,
a cloud scheduler + function, or a cron daemon on an always-on host.

---

## 4. Configuration

All configuration is supplied via environment variables / injected secrets.
The runner reads them at startup. No config file is committed with secrets.

| Key | Required | Purpose |
|---|---|---|
| `CALENDAR_CREDENTIALS` | Yes | Google service-account credential (JSON) for read access |
| `CALENDAR_ID` | Yes | Target calendar identifier (default: user's primary) |
| `CALENDAR_TZ` | No | IANA timezone for window computation & display (default `America/Santiago`) |
| `REPORT_SCOPE` | No | `upcoming` (default) or `past` week |
| `TELEGRAM_BOT_TOKEN` | Cond. | Enables Telegram delivery (with chat id) |
| `TELEGRAM_CHAT_ID` | Cond. | Destination chat for Telegram |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `MAIL_TO` | Cond. | Enables email delivery |
| `LLM_API_KEY` | No | Enables AI-rewritten summary; absent → factual list only |
| `REPORT_LANGUAGE` | No | Output language for the summary (default `Spanish`) |

A delivery channel is **active iff** its full set of required keys is present.
At least one delivery channel must be active or the run fails (see §9).

---

## 5. Authentication & Authorization

- **Google Calendar:** use a service account with a read-only Calendar scope.
  The user shares the target calendar with the service account's email at
  "see all event details" level. Rationale: headless, no interactive OAuth, no
  refresh-token expiry to manage.
- **Least privilege:** read-only scope; the service account must not be granted
  write or admin permissions.
- **Telegram:** a bot token obtained from BotFather; the destination chat id is
  resolved once during setup.
- **Email:** SMTP credentials; for Gmail, an app-specific password (not the
  account password). TLS (STARTTLS) required.
- **LLM:** API key for the chosen provider.

---

## 6. Time Window Computation

Given the current instant in `CALENDAR_TZ`:

- **`upcoming` scope (default):** window = next Monday 00:00:00 (inclusive)
  through the following Monday 00:00:00 (exclusive). If today is Monday, the
  window starts today.
- **`past` scope:** the most recently completed Monday–Sunday block.
- All boundaries are computed in `CALENDAR_TZ`, not UTC, to avoid off-by-one-day
  errors at week edges.

---

## 7. Calendar Reading

- Query events within `[window_start, window_end)` for `CALENDAR_ID`.
- **Expand recurring events** into individual instances (single-events mode), so
  a daily recurring item appears as one entry per day.
- **Order** results by start time ascending.
- **Paginate** until all results are retrieved (do not assume a single page).
- **Exclude** events with a cancelled status.
- **Handle two event shapes:**
  - *Timed events* — have explicit start/end datetimes (with timezone).
  - *All-day events* — have date-only start/end; render as "all day", excluded
    from hour totals.
- Convert all timed events to `CALENDAR_TZ` for display.

---

## 8. Summarization

### 8.1 Deterministic (always produced)
Group events by calendar day across the window. For each day in the window:
- If it has events: list each as `start–end  title` (timed) or `title — all
  day`.
- If empty: mark the day as free.

Compute aggregates:
- Total number of events.
- Total scheduled time (sum of timed-event durations), shown as hours/minutes.

Output is plain text, scannable on a phone screen, with a header line stating
the date range. This factual text is the canonical artifact and the fallback.

### 8.2 Optional AI rewrite
If `LLM_API_KEY` is present:
- Feed the deterministic factual text to the LLM with a system instruction to
  produce a short, friendly briefing in `REPORT_LANGUAGE`, grouping sensibly,
  naming the busiest day, stating total committed hours, and calling out free
  days.
- **Hard constraint:** the model must not invent events absent from the input.
  The factual text is the sole source of truth.
- Use a small/cheap model tier (summarization is low-complexity).
- Bound output length (short — fits a notification).
- On any LLM error or empty output, **fall back** to the deterministic text;
  an AI failure must never block delivery.

---

## 9. Delivery (Dispatcher)

- Each active channel receives the final summary text.
- **Telegram:** send a message to `TELEGRAM_CHAT_ID` via the bot. Plain text.
- **Email:** send a message to `MAIL_TO` over SMTP+STARTTLS; the subject is the
  summary's header/date-range line.
- **Multi-channel:** if both are configured, deliver to both; one channel's
  failure should not prevent the other from being attempted.
- **No active channel:** the run fails with a clear error (misconfiguration).

---

## 10. Error Handling & Observability

- **Fail loud on config errors:** missing required credentials, no active
  delivery channel → non-zero exit with a descriptive message.
- **Calendar/API errors:** surface as run failures (the scheduler's failure
  notification is the alerting mechanism).
- **LLM errors:** swallowed → fall back to factual text (degrade gracefully).
- **Per-channel delivery errors:** logged; attempt remaining channels; the run
  is considered failed if *all* attempted channels fail.
- **Logging:** print the generated summary and a per-channel send status to
  stdout so the scheduler's run log is self-explanatory.
- No secrets may be logged.

---

## 11. Security & Privacy

- Secrets only via the platform's secret store / injected env; never committed.
- Calendar access is read-only and least-privilege.
- Calendar data leaves the boundary only to: (a) the chosen delivery channels,
  and (b) the LLM provider *if* the AI option is enabled — note this to the user
  as a data-sharing consideration.
- Email uses TLS; tokens transmitted only over HTTPS.

---

## 12. Acceptance Criteria

1. On the scheduled trigger, with valid Google credentials, the system fetches
   the correct Monday–Sunday window in the configured timezone.
2. Recurring events appear as one instance per occurrence within the window.
3. All-day and timed events both render correctly; hour totals exclude all-day.
4. A week with no events yields a valid "no events" summary, still delivered.
5. With only Telegram configured, the summary arrives in Telegram; with only
   email configured, it arrives by email; with both, it arrives in both.
6. With `LLM_API_KEY` set, the delivered text is the AI narrative in
   `REPORT_LANGUAGE`; with it unset, the delivered text is the factual list.
7. An induced LLM failure still results in delivery of the factual list.
8. Manual on-demand invocation produces the same result as a scheduled run.
9. Missing all delivery config causes a clear, non-zero failure.

---

## 13. Test Plan (summary)

- **Unit:** week-boundary computation across DST transitions and the Monday
  edge case; event parsing for timed vs all-day; duration aggregation.
- **Integration:** against a test calendar containing a recurring event, an
  all-day event, and an empty day; verify summary correctness.
- **Channel:** dry-run each dispatcher with sandbox credentials.
- **Degradation:** force LLM error, assert factual fallback delivered.
- **Config matrix:** Telegram-only, email-only, both, neither (expect failure).

---

## 14. Future Extensions (out of scope for v1)

- Multiple source calendars merged into one report.
- Additional cadences (daily / monthly) sharing the same core.
- Per-day "focus time" suggestions derived from gaps.
- Localized formatting beyond language (date/number conventions).
- Delivery to additional channels (push app, chat platforms).