#!/usr/bin/env python3
"""
Weather Notifier
================

Sends a daily Telegram message with the forecast for three parts of a day
(morning / midday / night), each annotated with a clothing recommendation
(polera / polera + camisa / chaqueta) and a rain flag.

Run on a Raspberry Pi from cron. See Instructions.md for the full spec.

Telegram credentials and delivery live in `telegram_notifier.py`; this file
only handles the weather logic and message formatting.
"""

from datetime import datetime, timedelta

import requests

import telegram_notifier

# === Configuration (Instructions.md §5) =====================================

# Location (default: Santiago, Chile)
LATITUDE = -33.4489
LONGITUDE = -70.6693
TIMEZONE = "America/Santiago"

# Which day to report: 1 = tomorrow (default), 0 = today.
DAY_OFFSET = 1

# Day segments. Each entry: label, icon, display string, and the 24h hours
# whose values are combined (averaged for temperature, max for rain).
SEGMENTS = [
    {"label": "Mañana",   "icon": "🌅", "display": "6-7:00",   "hours": [6, 7]},
    {"label": "Mediodía", "icon": "☀️", "display": "14:00",    "hours": [14]},
    {"label": "Noche",    "icon": "🌙", "display": "21-22:00", "hours": [21, 22]},
]

# Clothing thresholds on feels-like temperature (°C).
TSHIRT_MIN = 21  # feels-like >= TSHIRT_MIN -> solo polera
SHIRT_MIN = 15   # feels-like >= SHIRT_MIN  -> polera + camisa (else chaqueta)

# Rain probability (%) at/above which we flag rain.
RAIN_THRESHOLD = 40

# --- Open-Meteo API ---------------------------------------------------------
API_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = (
    "temperature_2m,apparent_temperature,"
    "precipitation_probability,precipitation"
)
TIMEOUT = 15


# === Forecast retrieval =====================================================

def fetch_forecast():
    """Fetch the hourly forecast object from Open-Meteo.

    Raises requests.RequestException on network/API failure (captured by cron).
    """
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": HOURLY_VARS,
        "timezone": TIMEZONE,
        "forecast_days": DAY_OFFSET + 1,
    }
    response = requests.get(API_URL, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()["hourly"]


# === Aggregation helpers ====================================================

def _average(values):
    """Mean of values, ignoring None. Returns None if all values are None."""
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _max_or_zero(values):
    """Max of values, treating None as 0. Returns 0 for an empty list."""
    return max((v if v is not None else 0) for v in values) if values else 0


def target_date(times):
    """Local date to report, derived from the first hourly timestamp.

    Open-Meteo returns local time when `timezone` is set, so times[0] is the
    local midnight of "today"; add DAY_OFFSET to reach the reported day.
    """
    today = datetime.fromisoformat(times[0]).date()
    return today + timedelta(days=DAY_OFFSET)


def segment_data(hourly, day, segment):
    """Compute a segment's values, or None if none of its hours are present.

    Implements the "segment hours absent -> skip" edge case (Instructions §8).
    """
    index = {t: i for i, t in enumerate(hourly["time"])}
    rows = [
        index[f"{day.isoformat()}T{hour:02d}:00"]
        for hour in segment["hours"]
        if f"{day.isoformat()}T{hour:02d}:00" in index
    ]
    if not rows:
        return None

    return {
        "temp": _average([hourly["temperature_2m"][i] for i in rows]),
        "feels": _average([hourly["apparent_temperature"][i] for i in rows]),
        "rain_prob": _max_or_zero(
            [hourly["precipitation_probability"][i] for i in rows]
        ),
        "precip": _max_or_zero([hourly["precipitation"][i] for i in rows]),
    }


# === Decision logic =========================================================

def clothing(feels_like):
    """Return (icon, label) clothing recommendation for a feels-like temp."""
    if feels_like >= TSHIRT_MIN:
        return "👕", "Solo polera"
    if feels_like >= SHIRT_MIN:
        return "👕➕", "Polera + camisa"
    return "🧥", "Chaqueta"


def rain_line(data):
    """Return the rain warning line for a segment, or None if no rain flagged."""
    if data["rain_prob"] >= RAIN_THRESHOLD or data["precip"] > 0:
        return f"   🌧️ Lluvia {round(data['rain_prob'])}% — lleva paraguas"
    return None


# === Message assembly =======================================================

def build_message(hourly):
    """Build the full Telegram message text for the reported day."""
    day = target_date(hourly["time"])
    when = "mañana" if DAY_OFFSET == 1 else "hoy"
    lines = [f"Clima de {when} ({day.isoformat()})", ""]

    for segment in SEGMENTS:
        data = segment_data(hourly, day, segment)
        if data is None or data["feels"] is None:
            continue  # hours absent or no usable data -> skip segment

        icon, label = clothing(data["feels"])
        lines.append(f"{segment['icon']} {segment['label']} ({segment['display']})")
        lines.append(
            f"   🌡️ {round(data['temp'])}°C "
            f"(sensación {round(data['feels'])}°C)"
        )
        lines.append(f"   {icon} {label}")

        warning = rain_line(data)
        if warning:
            lines.append(warning)
        lines.append("")

    return "\n".join(lines).rstrip()


# === Entry point ============================================================

def main():
    # Fail fast with an explicit error before doing any work if creds missing.
    telegram_notifier.require_credentials()

    hourly = fetch_forecast()
    message = build_message(hourly)
    telegram_notifier.send_message(message)


if __name__ == "__main__":
    main()
