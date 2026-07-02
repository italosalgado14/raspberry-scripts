"""
Configuration loading & validation (SPEC §4, §9, §10).

This is the single place that reads the environment, decides which delivery
channels are active, and fails loud on misconfiguration. Secrets come only from
the environment (optionally seeded from a `.env` file next to the scripts) and
are never hard-coded or logged here.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Load a `.env` sitting next to this script, if present. `python-dotenv` is
# optional at runtime: if it (or the file) is absent we fall back to whatever is
# already in the environment. Real env vars always take precedence over `.env`,
# so the same code works on a dev machine and on the Pi.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


# --- Defaults (SPEC §4) -----------------------------------------------------
DEFAULT_TZ = "America/Santiago"
DEFAULT_SCOPE = "upcoming"
DEFAULT_LANGUAGE = "Spanish"
DEFAULT_LLM_MODEL = "claude-haiku-4-5"  # small/cheap tier (SPEC §8.2)
DEFAULT_SMTP_PORT = 587  # STARTTLS submission port

VALID_SCOPES = ("upcoming", "past")


@dataclass(frozen=True)
class Config:
    # Calendar (required)
    calendar_credentials: str | None
    calendar_id: str | None
    calendar_tz: str
    report_scope: str
    report_language: str
    # Telegram (conditional)
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    # Email (conditional)
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_pass: str | None
    mail_to: str | None
    # LLM (optional)
    llm_api_key: str | None
    llm_model: str


def _get(name: str, default: str | None = None) -> str | None:
    """Read an env var, treating empty/whitespace as absent."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def load_config() -> Config:
    """Read configuration from the environment into a Config object."""
    port_raw = _get("SMTP_PORT")
    try:
        smtp_port = int(port_raw) if port_raw else DEFAULT_SMTP_PORT
    except ValueError:
        sys.exit(f"ERROR: SMTP_PORT must be an integer, got {port_raw!r}.")

    return Config(
        calendar_credentials=_get("CALENDAR_CREDENTIALS"),
        calendar_id=_get("CALENDAR_ID"),
        calendar_tz=_get("CALENDAR_TZ", DEFAULT_TZ),
        report_scope=(_get("REPORT_SCOPE", DEFAULT_SCOPE) or DEFAULT_SCOPE).lower(),
        report_language=_get("REPORT_LANGUAGE", DEFAULT_LANGUAGE),
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_get("TELEGRAM_CHAT_ID"),
        smtp_host=_get("SMTP_HOST"),
        smtp_port=smtp_port,
        smtp_user=_get("SMTP_USER"),
        smtp_pass=_get("SMTP_PASS"),
        mail_to=_get("MAIL_TO"),
        llm_api_key=_get("LLM_API_KEY"),
        llm_model=_get("LLM_MODEL", DEFAULT_LLM_MODEL),
    )


# --- Channel activation (SPEC §4: a channel is active iff its full key set is
# present) -------------------------------------------------------------------
def telegram_enabled(cfg: Config) -> bool:
    return bool(cfg.telegram_bot_token and cfg.telegram_chat_id)


def email_enabled(cfg: Config) -> bool:
    return bool(
        cfg.smtp_host and cfg.smtp_user and cfg.smtp_pass and cfg.mail_to
    )


def llm_enabled(cfg: Config) -> bool:
    return bool(cfg.llm_api_key)


def active_channels(cfg: Config) -> list[str]:
    channels = []
    if telegram_enabled(cfg):
        channels.append("telegram")
    if email_enabled(cfg):
        channels.append("email")
    return channels


def validate_calendar(cfg: Config) -> None:
    """Fail loud on missing calendar credentials or an invalid scope (§10).

    This is all that a read-only test (``--raw`` / ``--dry-run``) needs.
    """
    missing = [
        name
        for name, value in (
            ("CALENDAR_CREDENTIALS", cfg.calendar_credentials),
            ("CALENDAR_ID", cfg.calendar_id),
        )
        if not value
    ]
    if missing:
        sys.exit(
            "ERROR: missing required environment variable(s): "
            + ", ".join(missing)
            + ".\nCopy .env.example to .env and fill it in — see the README."
        )

    if cfg.report_scope not in VALID_SCOPES:
        sys.exit(
            f"ERROR: REPORT_SCOPE must be one of {VALID_SCOPES}, "
            f"got {cfg.report_scope!r}."
        )


def validate_channels(cfg: Config) -> None:
    """Fail loud if no delivery channel is fully configured (SPEC §9, §10)."""
    if not active_channels(cfg):
        sys.exit(
            "ERROR: no delivery channel is configured. Enable Telegram "
            "(TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) and/or email "
            "(SMTP_HOST + SMTP_USER + SMTP_PASS + MAIL_TO). "
            "At least one channel is required."
        )


def validate(cfg: Config) -> None:
    """Full validation for a delivering run: calendar access + a channel."""
    validate_calendar(cfg)
    validate_channels(cfg)
