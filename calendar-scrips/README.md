# Weekly Calendar Report

An unattended Raspberry Pi (or CI) service that, once per week, reads your Google
Calendar, builds a human-readable summary of the week, and delivers it to your
phone over **Telegram** and/or **email**. Read-only, stateless, effectively zero
cost.

> Full specification: [SPEC.md](SPEC.md).

It fetches the upcoming Monday→Monday week, lists each day's events (or marks it
free), totals your committed hours, and sends a single message. An **optional**
AI rewrite turns the factual list into a short friendly briefing; if the AI is
not configured (or fails), the factual list is delivered as-is.

## Example output (factual)

```
📅 Agenda · semana del 15 jun al 21 jun 2026

Lunes 15 jun
   09:00–09:30  Standup
   14:00–15:00  Almuerzo con Ana
Martes 16 jun
   18:00–19:30  Gym
Miércoles 17 jun
   Feriado — todo el día
Jueves 18 jun
   — libre —
Viernes 19 jun
   10:00–11:00  1:1 con jefe
Sábado 20 jun
   — libre —
Domingo 21 jun
   — libre —

Total de eventos: 5
Tiempo agendado: 4h
```

## Files

| File | Purpose |
|------|---------|
| `calendar_report.py` | Main runner: config → window → fetch → summarize → dispatch. |
| `config.py` | Reads & validates all env vars; decides which channels are active; fails loud on misconfiguration. |
| `timewindow.py` | Pure Monday→Monday week-window computation (`upcoming` / `past`). |
| `calendar_reader.py` | Service-account auth + event fetch (recurring expansion, pagination, cancelled excluded). |
| `summarizer.py` | Deterministic factual report + optional Anthropic AI rewrite (graceful fallback). |
| `dispatcher.py` | Telegram + email (SMTP/STARTTLS) delivery; multi-channel, independent failures. |
| `models.py` | The normalized `Event` data model (dependency-free). |
| `tests/` | `pytest` unit tests: week boundaries, event parsing, summary aggregation. |
| `.env.example` | Template for credentials/config. Copy to `.env` and fill in. |
| `pyproject.toml` | Dependencies, managed with [uv](https://docs.astral.sh/uv/). |

## Setup

### 1. Install dependencies

```bash
# Install uv once (https://docs.astral.sh/uv/), then sync deps into .venv:
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### 2. Google service account (read-only Calendar)

The service account is a headless identity — no interactive OAuth, no refresh
tokens to babysit (SPEC §5).

1. In the [Google Cloud Console](https://console.cloud.google.com/), create (or
   pick) a project.
2. **APIs & Services → Library →** enable the **Google Calendar API**.
3. **APIs & Services → Credentials → Create credentials → Service account.**
   Give it a name; no roles needed.
4. Open the service account → **Keys → Add key → Create new key → JSON.**
   Download the JSON file. Copy its `client_email` (looks like
   `name@project.iam.gserviceaccount.com`).
5. **Share your calendar with that email.** In Google Calendar → your calendar's
   *Settings and sharing* → *Share with specific people* → add the service
   account email with **"See all event details"** (read-only).
6. Find your **calendar id**: same *Settings and sharing* page → *Integrate
   calendar → Calendar ID* (usually your account email). This is `CALENDAR_ID`.

Put the JSON key on the Pi (e.g. `service-account.json` next to the scripts — it
is gitignored) and point `CALENDAR_CREDENTIALS` at its path, **or** paste the
JSON content into `CALENDAR_CREDENTIALS` directly.

### 3. Pick at least one delivery channel

**Telegram** (set both):
1. In Telegram open [@BotFather](https://t.me/BotFather) → `/newbot` → copy the
   HTTP API token → `TELEGRAM_BOT_TOKEN`.
2. Send your new bot any message, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy
   `result[].message.chat.id` → `TELEGRAM_CHAT_ID`.

**Email** (set all four — `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `MAIL_TO`):
For Gmail, create an **app-specific password** (Google Account → Security →
2-Step Verification → App passwords) and use it as `SMTP_PASS`. Host
`smtp.gmail.com`, port `587` (STARTTLS).

### 4. Optional AI rewrite

Set `LLM_API_KEY` (Anthropic) to get a short narrative briefing instead of the
plain list. Leave it unset for the factual list. **Note:** enabling this sends
your calendar summary to the LLM provider (SPEC §11).

### 5. Configure & test

```bash
cp .env.example .env
chmod 600 .env
#   ...edit .env with your real values
```

**Test the Google side first** — these two modes need only the calendar
credentials (no Telegram/email), so you can confirm the read works before
wiring up delivery:

```bash
uv run calendar_report.py --raw       # raw Google Calendar API events, as JSON
uv run calendar_report.py --dry-run   # the formatted weekly summary, NOT sent
```

Then a full run that actually delivers:

```bash
uv run calendar_report.py             # same code path as the scheduled run
```

The full run prints the summary and per-channel send status to stdout, then sends.

## Configuration

All settings come from the environment / `.env` (SPEC §4). A delivery channel is
active **iff** its full key set is present; the run fails if none are.

| Key | Required | Default | Purpose |
|-----|----------|---------|---------|
| `CALENDAR_CREDENTIALS` | yes | — | Service-account JSON: a file path **or** the JSON itself |
| `CALENDAR_ID` | yes | — | Calendar to read (usually your account email) |
| `CALENDAR_TZ` | no | `America/Santiago` | IANA tz for the window & display |
| `REPORT_SCOPE` | no | `upcoming` | `upcoming` or `past` week |
| `REPORT_LANGUAGE` | no | `Spanish` | Output language |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | cond. | — | Enable Telegram (need both) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `MAIL_TO` | cond. | port `587` | Enable email |
| `LLM_API_KEY` | no | — | Enable AI rewrite (Anthropic) |
| `LLM_MODEL` | no | `claude-haiku-4-5` | Override the AI model |

## Scheduling (cron)

Run Sunday evening to preview the week ahead (SPEC §3):

```cron
0 19 * * 0 cd /home/pi/raspberry-scripts/calendar-scrips && /home/pi/.local/bin/uv run calendar_report.py >> /home/pi/calendar-report.log 2>&1
```

`cron` has a minimal `PATH`, so use the **absolute path** to `uv` (`which uv`)
and `cd` into the project so `uv run` finds `pyproject.toml` and the script finds
`.env`. Credentials load automatically — no need to source anything.

> **Timezone caveat (SPEC §3):** the cron expression fires in the host's local
> time. If your host runs in **UTC** (many CI runners do), offset the hour for
> `America/Santiago` (UTC−4, or −3 in DST) — e.g. `0 23 * * 0`. The cadence is
> approximate; the exact minute is not critical.
>
> For resilience against missed runs (reboots/downtime), a `systemd` timer with
> `Persistent=true` is an alternative to cron.

## Tests

```bash
uv run --group dev pytest
```

Covers the unit-testable core (SPEC §13): week-boundary computation incl. the
Monday edge case and DST, timed-vs-all-day event parsing, and duration
aggregation. The Calendar fetch and the dispatchers are exercised manually
against real (sandbox) credentials.

## Notes & limitations

- Read-only and least-privilege by design (SPEC §5, §11). Calendar data leaves
  the boundary only to your chosen channels and — if enabled — the LLM provider.
- No secrets are logged; channel error messages are scrubbed of the bot token
  and the SMTP password before printing.
- An AI failure never blocks delivery — it falls back to the factual list.
- Multi-day all-day events appear on each day they cover; they are excluded from
  hour totals.
