"""Unit tests for slot math and date/time helpers (pure, no I/O)."""

from __future__ import annotations

from datetime import date, datetime

from municipal_mcp.slots import (
    format_datetime_it,
    generate_day_slots,
    intervals_overlap,
    is_open_day,
    parse_datetime,
)


def _next_open_day() -> date:
    day = date(2026, 6, 15)
    while not is_open_day(day):
        day = date.fromordinal(day.toordinal() + 1)
    return day


def test_open_and_closed_days():
    # With default config (Mon-Fri), Saturday and Sunday are closed.
    assert is_open_day(date(2026, 6, 13)) is False  # Saturday
    assert is_open_day(date(2026, 6, 14)) is False  # Sunday
    assert is_open_day(date(2026, 6, 15)) is True    # Monday


def test_generate_day_slots_count_default_hours():
    # Default 09:00-12:30 with 30-minute slots gives 7 slots.
    slots = generate_day_slots(_next_open_day())
    assert len(slots) == 7
    assert slots[0].hour == 9 and slots[0].minute == 0


def test_no_slots_on_closed_day():
    assert generate_day_slots(date(2026, 6, 14)) == []  # Sunday


def test_intervals_overlap():
    a0 = datetime(2026, 6, 15, 9, 0)
    a1 = datetime(2026, 6, 15, 9, 30)
    b0 = datetime(2026, 6, 15, 9, 15)
    b1 = datetime(2026, 6, 15, 9, 45)
    assert intervals_overlap(a0, a1, b0, b1) is True
    # Touching at the boundary does not overlap.
    assert intervals_overlap(a0, a1, a1, datetime(2026, 6, 15, 10, 0)) is False


def test_parse_datetime_adds_timezone():
    parsed = parse_datetime("2026-06-15T09:30")
    assert parsed.tzinfo is not None
    assert parsed.hour == 9 and parsed.minute == 30


def test_format_datetime_it_is_italian():
    text = format_datetime_it(parse_datetime("2026-06-15T09:30"))
    assert "giugno" in text
    assert "alle 09:30" in text
