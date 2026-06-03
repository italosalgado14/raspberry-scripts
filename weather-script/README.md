# Weather Notifier

A small Raspberry Pi service that sends one daily Telegram message with the
forecast for three parts of a day — **morning / midday / night** — each with a
clothing recommendation (*polera* / *polera + camisa* / *chaqueta*) and a rain
flag.

It fetches the forecast from [Open-Meteo](https://open-meteo.com/) (free, no API
key), decides what to wear from the *feels-like* temperature, and delivers a
single Markdown message over Telegram. No conversation, no LLM, no web UI — just
"how should I dress today?" on your phone.

> Full specification: [Instructions.md](Instructions.md).

## Example message

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

Segments with no rain simply omit the rain line.

## Files

| File | Purpose |
|------|---------|
| `weather_notify.py` | Main script: fetch forecast → derive clothing + rain → build the message. All weather/location config lives in the constants at the top. |
| `telegram_notifier.py` | Telegram credentials & delivery, isolated from the weather logic. Reads the token + chat id from the environment / `.env` and sends the message. |
| `Instructions.md` | The full specification (requirements, thresholds, data source, edge cases). |
| `.env.example` | Template for the credentials file. Copy to `.env` and fill in your Telegram token + chat id. |
| `pyproject.toml` | Project metadata and dependencies (`requests`, `python-dotenv`), managed with [uv](https://docs.astral.sh/uv/). |
| `.gitignore` | Keeps secrets (`.env`), logs, and caches out of git. |

## Setup

```bash
# 1. Install uv once (https://docs.astral.sh/uv/), then sync dependencies
#    from pyproject.toml into a project-local virtualenv (.venv):
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# 2. Add your Telegram credentials (see "Telegram bot" below):
cp .env.example .env
chmod 600 .env
#    ...edit .env with your real TELEGRAM_TOKEN and TELEGRAM_CHAT_ID

# 3. Test once. The script auto-loads .env; uv run uses the synced environment:
uv run weather_notify.py
```

## Telegram bot

The bot token and chat id are read from the environment, loaded from a `.env`
file sitting next to the scripts (`telegram_notifier.py` loads it automatically
via `python-dotenv`). Real exported environment variables take precedence over
`.env`, so the same code works on a dev machine and on the Pi.

1. **Create the bot.** In Telegram, open [@BotFather](https://t.me/BotFather),
   send `/newbot`, and follow the prompts (a name, then a unique username ending
   in `bot`). BotFather replies with an **HTTP API token** like
   `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` → this is `TELEGRAM_TOKEN`.
2. **Find your chat id.** Send your new bot any message (e.g. "hi"), then open
   `https://api.telegram.org/bot<TELEGRAM_TOKEN>/getUpdates` in a browser. In the
   JSON, copy `result[].message.chat.id` → this is `TELEGRAM_CHAT_ID`.
3. **Save them** in `.env`:

   ```dotenv
   TELEGRAM_TOKEN=123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   TELEGRAM_CHAT_ID=987654321
   ```

`.env` is gitignored — never commit it. If either value is missing, the script
exits immediately with an explicit error before doing any work.

## Configuration

- **Weather & location** — edit the constants at the top of `weather_notify.py`:

  | Constant | Default | Meaning |
  |----------|---------|---------|
  | `LATITUDE`, `LONGITUDE` | Santiago (`-33.4489`, `-70.6693`) | Location |
  | `TIMEZONE` | `America/Santiago` | IANA timezone |
  | `DAY_OFFSET` | `1` | `1` = tomorrow, `0` = today |
  | `SEGMENTS` | 06–07 / 14 / 21–22 | Time slots reported (label, icon, hours) |
  | `TSHIRT_MIN` | `21` | Feels-like ≥ this → solo polera 👕 |
  | `SHIRT_MIN` | `15` | Feels-like ≥ this → polera + camisa 👕➕ (else chaqueta 🧥) |
  | `RAIN_THRESHOLD` | `40` | Rain-probability % at/above which rain is flagged |

  Multi-hour segments **average** temperature and take the **max** rain
  probability/amount over the window. The clothing choice uses *feels-like*
  (`apparent_temperature`), not air temperature. Rain is flagged when
  probability ≥ `RAIN_THRESHOLD` **or** any precipitation is forecast.

- **Telegram** — bot token and chat id come from `.env` (see above); all delivery
  logic lives in `telegram_notifier.py`.

## Scheduling (cron)

Run in the evening so tomorrow's forecast is ready the night before:

```cron
0 21 * * * cd /home/pi/raspberry-scripts/weather-script && /home/pi/.local/bin/uv run weather_notify.py >> /home/pi/weather.log 2>&1
```

`cron` runs with a minimal `PATH`, so the line uses the **absolute path** to `uv`
(check yours with `which uv`) and `cd`s into the project directory so `uv run`
finds `pyproject.toml` and the script finds `.env`. Credentials load
automatically — no need to source any env file.

> For resilience against missed runs (reboots, downtime), a `systemd` timer with
> `Persistent=true` is an alternative to cron.

## Tuning notes

- Raise `TSHIRT_MIN` / `SHIRT_MIN` a couple of degrees if you run cold.
- To be more cautious on cold mornings, switch the clothing input from the
  segment **average** to the **minimum** feels-like in each window.
- Adjust the `SEGMENTS` hours to match your actual schedule.
