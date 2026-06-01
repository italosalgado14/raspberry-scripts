"""
Telegram configuration and delivery.

This module isolates everything Telegram-specific so the rest of the
project never has to know how messages are sent:

  * reading the bot credentials from the environment
  * validating they are present
  * sending a Markdown message to the configured chat

Credentials are NEVER hard-coded here. They are read from the environment,
loaded from a local `.env` file (see `.env.example`) that sits next to this
script:

    TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
    TELEGRAM_CHAT_ID=987654321

Real environment variables (e.g. exported in a shell) take precedence over
`.env`, so the same code works on a dev machine and on the Pi.

See Instructions.md §5 and §7 for how to obtain these values.
"""

import os
import sys
from pathlib import Path

import requests

# Load credentials from a `.env` file sitting next to this script, if present.
# `python-dotenv` is optional at runtime: if it (or the file) is absent we fall
# back to whatever is already in the environment. Existing env vars are never
# overridden by the file.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# --- Configuration ----------------------------------------------------------
# Secrets come from the environment / .env file (see `.env.example`).
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Telegram Bot API endpoint template and network timeout (seconds).
API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT = 15

# Default Telegram parse mode for outgoing messages.
PARSE_MODE = "Markdown"


def require_credentials():
    """Exit with an explicit error message if the bot credentials are missing.

    Implements the "Missing token / chat id -> exit with explicit error
    message" edge case from Instructions.md §8.
    """
    missing = [
        name
        for name, value in (
            ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
            ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
        )
        if not value
    ]
    if missing:
        sys.exit(
            "ERROR: missing required environment variable(s): "
            + ", ".join(missing)
            + ".\nAdd them to a .env file next to the script "
            "(copy .env.example to .env):\n"
            "  TELEGRAM_TOKEN=123456:ABC-DEF...\n"
            "  TELEGRAM_CHAT_ID=987654321"
        )


def send_message(text, parse_mode=PARSE_MODE):
    """Send `text` to the configured chat.

    Raises requests.HTTPError / requests.RequestException on API or network
    failure so the caller (and cron) can capture it in the log.
    """
    require_credentials()
    response = requests.post(
        API_URL.format(token=TELEGRAM_TOKEN),
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()
