"""
Delivery channels (SPEC §9).

One adapter per channel; channels auto-enable from configuration. Each active
channel is attempted independently — one channel's failure never blocks the
others — and the run is considered failed only if *every* attempted channel
fails. Per-channel status is printed so the scheduler's log is self-explanatory.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import requests

from config import email_enabled, telegram_enabled

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_TIMEOUT = 20
SMTP_TIMEOUT = 30


def _redact(text: str, *secrets) -> str:
    """Strip any present secret values from a string before it is logged.

    Error messages (e.g. requests' HTTPError embeds the bot-token URL) can carry
    secrets; nothing logged or raised from this module may expose them
    (SPEC §10, §11).
    """
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def send_telegram(token, chat_id, text) -> None:
    """Send a plain-text Telegram message (SPEC §9). Raises on failure."""
    response = requests.post(
        TELEGRAM_API.format(token=token),
        data={"chat_id": chat_id, "text": text},  # plain text (no parse_mode)
        timeout=TELEGRAM_TIMEOUT,
    )
    response.raise_for_status()


def send_email(host, port, user, password, mail_to, subject, body) -> None:
    """Send an email over SMTP + STARTTLS (SPEC §9). Raises on failure."""
    message = EmailMessage()
    message["From"] = user
    message["To"] = mail_to
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT) as server:
        server.starttls(context=context)
        server.login(user, password)
        server.send_message(message)


def dispatch(report, cfg) -> dict:
    """Deliver ``report`` to every active channel.

    Returns ``{channel: "ok" | "error: ..."}`` and prints per-channel status.
    Raises ``RuntimeError`` (non-zero exit) if every attempted channel fails or
    if no channel is active (SPEC §9, §10).
    """
    statuses: dict[str, str] = {}

    if telegram_enabled(cfg):
        try:
            send_telegram(cfg.telegram_bot_token, cfg.telegram_chat_id, report.text)
            statuses["telegram"] = "ok"
        except Exception as exc:  # noqa: BLE001 — still attempt other channels
            statuses["telegram"] = f"error: {_redact(str(exc), cfg.telegram_bot_token)}"

    if email_enabled(cfg):
        try:
            send_email(
                cfg.smtp_host,
                cfg.smtp_port,
                cfg.smtp_user,
                cfg.smtp_pass,
                cfg.mail_to,
                report.header,  # subject = date-range line (SPEC §9)
                report.text,
            )
            statuses["email"] = "ok"
        except Exception as exc:  # noqa: BLE001 — still attempt other channels
            statuses["email"] = f"error: {_redact(str(exc), cfg.smtp_pass)}"

    for channel, status in statuses.items():
        print(f"[dispatch] {channel}: {status}")

    if not statuses:
        raise RuntimeError("no active delivery channel (misconfiguration)")
    if all(status != "ok" for status in statuses.values()):
        raise RuntimeError(f"all delivery channels failed: {statuses}")

    return statuses
