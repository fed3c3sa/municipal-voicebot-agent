"""Time helpers for the appointment calendar.

Everything here is pure (no database): timezone handling, slot-grid generation
within office hours, parsing of incoming date/time strings, and Italian-friendly
formatting. The database layer (bookings.py) builds on top of these.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import get_settings

_GIORNI = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
_MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def get_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().booking_timezone)


def appointment_duration() -> int:
    return get_settings().appointment_duration_minutes


def add_duration(start: datetime, minutes: int | None = None) -> datetime:
    """Return the end time for an appointment starting at `start`."""
    minutes = appointment_duration() if minutes is None else minutes
    return start + timedelta(minutes=minutes)


def is_open_day(day: date) -> bool:
    return day.weekday() in get_settings().open_weekdays


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Return the tz-aware start and end (exclusive) of a calendar day."""
    tz = get_timezone()
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def generate_day_slots(day: date) -> list[datetime]:
    """Return the tz-aware candidate slot start times for a day within office hours."""
    settings = get_settings()
    if not is_open_day(day):
        return []
    tz = get_timezone()
    duration = timedelta(minutes=settings.appointment_duration_minutes)
    open_dt = datetime.combine(day, settings.open_time, tzinfo=tz)
    close_dt = datetime.combine(day, settings.close_time, tzinfo=tz)

    slots: list[datetime] = []
    current = open_dt
    while current + duration <= close_dt:
        slots.append(current)
        current += duration
    return slots


def intervals_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """True when [start_a, end_a) and [start_b, end_b) intersect."""
    return start_a < end_b and start_b < end_a


def parse_datetime(text: str) -> datetime:
    """Parse a date/time string into a tz-aware datetime (assumes the booking tz).

    Accepts ISO formats such as "2026-06-15T09:30" or "2026-06-15 09:30".
    Raises ValueError if the string cannot be parsed.
    """
    parsed = datetime.fromisoformat(text.strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=get_timezone())
    return parsed


def parse_date(text: str) -> date:
    """Parse an ISO date string ("2026-06-15"). Raises ValueError if invalid."""
    return date.fromisoformat(text.strip())


def format_datetime_it(value: datetime) -> str:
    """Format a datetime in Italian, e.g. 'lunedi 15 giugno 2026 alle 09:30'."""
    local = value.astimezone(get_timezone())
    return (
        f"{_GIORNI[local.weekday()]} {local.day} {_MESI[local.month - 1]} "
        f"{local.year} alle {local:%H:%M}"
    )


def format_time_it(value: datetime) -> str:
    """Format only the time part in the booking timezone, e.g. '09:30'."""
    return f"{value.astimezone(get_timezone()):%H:%M}"
