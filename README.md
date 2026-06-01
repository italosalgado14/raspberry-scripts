# Weather Notifier

A small Raspberry Pi service that sends a daily Telegram message with the
forecast for three parts of the day (morning / midday / night), each with a
clothing recommendation and a rain flag. See [Instructions.md](Instructions.md)
for the full specification.

## Files

| File | Purpose |
|------|---------|
| `weather_notify.py` | Main script: fetch forecast → derive clothing + rain → build message. All weather config lives at the top. |
| `telegram_notifier.py` | **Telegram configuration & delivery**, isolated from the weather logic. Reads credentials from the environment and sends the message. |
| `.env.example` | Template for the credentials file. Copy to `.env` and fill in your Telegram token + chat id. |
| `pyproject.toml` | Project metadata and Python dependencies, managed with [uv](https://docs.astral.sh/uv/). |
| `.gitignore` | Keeps secrets (`.env`) and caches out of git. |

## Setup

```bash
# Install uv once (https://docs.astral.sh/uv/), then sync dependencies
# from pyproject.toml into a project-local virtualenv:
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Credentials (see "Configuring the Telegram bot" below)
cp .env.example .env
chmod 600 .env
# ...edit .env with your real TELEGRAM_TOKEN and TELEGRAM_CHAT_ID

# Test once (the script auto-loads .env; uv run uses the synced environment)
uv run weather_notify.py
```

## Configuring the Telegram bot

The bot token and chat id are read from a `.env` file in the project directory
(loaded automatically by `telegram_notifier.py`).

1. **Create the bot.** In Telegram, open [@BotFather](https://t.me/BotFather),
   send `/newbot`, and follow the prompts (a name, then a unique username
   ending in `bot`). BotFather replies with an **HTTP API token** that looks
   like `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` → this is
   `TELEGRAM_TOKEN`.
2. **Find your chat id.** Send your new bot any message (e.g. "hi"), then open
   in a browser: `https://api.telegram.org/bot<TELEGRAM_TOKEN>/getUpdates`.
   In the JSON, copy `result[].message.chat.id` → this is `TELEGRAM_CHAT_ID`.
3. **Save them.** Put both into `.env`:

   ```dotenv
   TELEGRAM_TOKEN=123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   TELEGRAM_CHAT_ID=987654321
   ```

`.env` is gitignored — never commit it. Real exported environment variables
take precedence over `.env`, so you can override per-run if needed.

## Scheduling (cron)

Run in the evening so tomorrow's forecast is ready the night before:

```cron
0 21 * * * cd /home/pi/raspberry-scripts && /home/pi/.local/bin/uv run weather_notify.py >> /home/pi/weather.log 2>&1
```

> `cron` runs with a minimal `PATH`, so the cron line uses the absolute path to
> `uv` (check yours with `which uv`) and `cd`s into the project directory so
> `uv run` finds `pyproject.toml` and the script finds `.env`. No need to source
> any env file — `.env` is loaded automatically.

## Configuration

- **Weather** (location, day segments, clothing/rain thresholds, `DAY_OFFSET`):
  edit the constants at the top of `weather_notify.py`.
- **Telegram** (bot token, chat id): set in `.env` (see "Configuring the
  Telegram bot" above); the delivery logic lives in `telegram_notifier.py`.
