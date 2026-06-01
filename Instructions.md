# Weather Notifier — Specification

A Raspberry Pi service that sends a daily Telegram message with the forecast for three parts of the day, each annotated with a clothing recommendation (*polera* / *polera + camisa* / *chaqueta*) and a rain flag.

---

## 1. Purpose & Scope

| | |
|---|---|
| **Goal** | Tell the user, on their phone, how to dress for the day before they leave home. |
| **Channel** | Telegram (single recipient). |
| **Host** | Raspberry Pi, triggered by `cron`. |
| **Default location** | Santiago, Chile (`-33.4489, -70.6693`, tz `America/Santiago`). |

**In scope:** fetch forecast → derive clothing + rain → send one Telegram message.

**Out of scope (explicitly):** conversational interaction, AI/LLM agents, multiple users, multiple channels, web UI, historical logging beyond a local cron log.

---

## 2. Functional Requirements

### 2.1 Day reported
- Configurable via `DAY_OFFSET`: `1` = tomorrow (default), `0` = today.

### 2.2 Day segments
The message reports exactly three time slots. Each slot is defined by the representative hours below; multi-hour slots are averaged.

| Segment   | Label      | Hours (24h) |
|-----------|------------|-------------|
| Morning   | Mañana     | 06:00–07:00 |
| Midday    | Mediodía   | 14:00       |
| Night     | Noche      | 21:00–22:00 |

For each segment the system computes:
- **Air temperature** (`temperature_2m`)
- **Feels-like temperature** (`apparent_temperature`) — used for the clothing decision
- **Rain probability** (`precipitation_probability`, max over the window)
- **Precipitation amount** (`precipitation`, max over the window)

### 2.3 Clothing decision
Based on **feels-like** temperature (chosen over air temp because it better reflects cold, windy mornings):

| Feels-like (°C) | Recommendation        | Icon |
|-----------------|-----------------------|------|
| ≥ 21            | Solo polera           | 👕   |
| 15 – 20.9       | Polera + camisa       | 👕➕ |
| < 15            | Chaqueta              | 🧥   |

Thresholds are user-tunable (`TSHIRT_MIN`, `SHIRT_MIN`).

### 2.4 Rain flag
A rain line is added to a segment when **rain probability ≥ 40%** *or* any precipitation amount is forecast for that segment. Threshold tunable via `RAIN_THRESHOLD`.

---

## 3. Output — Telegram Message Format

Sent with `parse_mode = Markdown`. Empty/zero-rain segments simply omit the rain line.

```
Clima de mañana (2026-06-02)

🌅 Mañana (6-7:00)
   🌡️ 8°C (sensación 6°C)
   🧥 Chaqueta
   🌧️ Lluvia 70% — lleva paraguas

☀️ Mediodía (14:00)
   🌡️ 19°C (sensación 19°C)
   👕➕ Polera + camisa

🌙 Noche (21-22:00)
   🌡️ 11°C (sensación 9°C)
   🧥 Chaqueta
```

---

## 4. Data Source

**Open-Meteo** — free, no API key required.

- **Endpoint:** `https://api.open-meteo.com/v1/forecast`
- **Query parameters:**

| Param | Value |
|-------|-------|
| `latitude` / `longitude` | location coordinates |
| `hourly` | `temperature_2m,apparent_temperature,precipitation_probability,precipitation` |
| `timezone` | `America/Santiago` |
| `forecast_days` | `DAY_OFFSET + 1` |

Response is an `hourly` object holding parallel arrays (`time`, `temperature_2m`, …) indexed positionally.

---

## 5. Configuration

All configuration lives at the top of the script; secrets come from environment variables.

| Name | Type | Default | Meaning |
|------|------|---------|---------|
| `LATITUDE`, `LONGITUDE` | float | Santiago | Location |
| `TIMEZONE` | str | `America/Santiago` | IANA tz |
| `DAY_OFFSET` | int | `1` | 1 = tomorrow, 0 = today |
| `SEGMENTS` | list | see §2.2 | (name, icon, hours) per slot |
| `TSHIRT_MIN` | int | `21` | feels-like ≥ → solo polera |
| `SHIRT_MIN` | int | `15` | feels-like ≥ → polera + camisa |
| `RAIN_THRESHOLD` | int | `40` | rain-probability % to flag rain |
| `TELEGRAM_TOKEN` | env | — | bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | env | — | recipient chat id |

---

## 6. Scheduling

`cron` on the Pi, run in the evening so tomorrow's forecast is ready the night before.

```cron
0 21 * * * cd /home/pi/raspberry-scripts && /home/pi/.local/bin/uv run weather_notify.py >> /home/pi/weather.log 2>&1
```

(Use the absolute path to `uv` — `which uv` — since `cron` has a minimal `PATH`,
and `cd` into the project so `uv run` finds `pyproject.toml` and the script finds
`.env`. Credentials are loaded automatically from `.env`; no need to source it.)

`.env` (in the project directory, copied from `.env.example`):
```dotenv
TELEGRAM_TOKEN=123:abc
TELEGRAM_CHAT_ID=456
```

> For resilience against missed runs (reboots, downtime), a `systemd` timer with `Persistent=true` is an alternative to cron.

---

## 7. Setup (one-time)

1. Install [uv](https://docs.astral.sh/uv/), then `uv sync` (installs deps from `pyproject.toml`).
2. Create the Telegram bot via **@BotFather** → `/newbot` → copy token.
3. Send the bot any message, open `https://api.telegram.org/bot<TOKEN>/getUpdates`, copy `chat.id`.
4. Put token + chat id in `.env` (copy `.env.example` to `.env`).
5. Test once: `uv run weather_notify.py`.
6. Add the cron line from §6.

---

## 8. Error Handling & Edge Cases

| Case | Behaviour |
|------|-----------|
| Missing token / chat id | Exit with explicit error message. |
| Network / API failure | `requests` raises; cron captures it in `weather.log`. |
| Segment hours absent in response | Segment is skipped (not fabricated). |
| `null` values in arrays | Treated as 0 / ignored in averages. |

**Possible hardening (not yet implemented):** retry with backoff on network failure; alert if no message sent for N days.

---

## 9. Tuning Notes

- Raise `TSHIRT_MIN` / `SHIRT_MIN` a couple of degrees if you run cold.
- Multi-hour segments currently **average** their hours. To be more cautious, switch the clothing input to the **minimum** feels-like in each window.
- Adjust `SEGMENTS` hours to match your actual schedule.