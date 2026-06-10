"""Unit tests for the appointment tools that do not require a database.

These cover the validation and Italian-message paths that return before any DB
access (missing fields, bad input, formatting helpers). The full create/cancel
flow against Postgres lives in test_tools_integration.py.
"""

from __future__ import annotations

from fastmcp import Client

from municipal_mcp.models import Appointment
from municipal_mcp.server import build_server
from municipal_mcp.slots import add_duration, parse_datetime
from municipal_mcp.tools.appointments import _format_appointment, _slots_message


def tool_text(result) -> str:
    data = getattr(result, "data", None)
    if isinstance(data, str):
        return data
    return result.content[0].text


def test_format_appointment_is_italian():
    start = parse_datetime("2026-06-15T09:30")
    appointment = Appointment(
        id=7,
        citizen_name="Maria",
        citizen_surname="Rossi",
        phone="0432123456",
        reason="rinnovo CIE",
        start_at=start,
        end_at=add_duration(start, 30),
        duration_minutes=30,
        status="active",
    )
    text = _format_appointment(appointment)
    assert "Maria Rossi" in text
    assert "numero 7" in text
    assert "rinnovo CIE" in text


def test_slots_message_empty():
    assert "non ci sono orari" in _slots_message("il 14/6/2026", [])


def test_slots_message_lists_times():
    slots = [parse_datetime("2026-06-15T09:00"), parse_datetime("2026-06-15T09:30")]
    message = _slots_message("il 15/6/2026", slots)
    assert "09:00" in message and "09:30" in message


async def test_create_appointment_reports_missing_fields():
    async with Client(build_server()) as client:
        result = await client.call_tool("create_appointment", {"name": "Maria"})
        text = tool_text(result)
    assert "mi servono ancora" in text
    assert "il cognome" in text
    assert "il numero di telefono" in text


async def test_create_appointment_rejects_bad_datetime():
    async with Client(build_server()) as client:
        result = await client.call_tool(
            "create_appointment",
            {"name": "Maria", "surname": "Rossi", "phone": "0432", "start_at": "domani mattina"},
        )
        text = tool_text(result)
    assert "Non ho capito la data" in text


async def test_check_appointments_requires_a_filter():
    async with Client(build_server()) as client:
        result = await client.call_tool("check_appointments", {})
        text = tool_text(result)
    assert "almeno il numero di telefono" in text


async def test_get_available_slots_rejects_bad_date():
    async with Client(build_server()) as client:
        result = await client.call_tool("get_available_slots", {"date": "15 giugno"})
        text = tool_text(result)
    assert "La data non e' valida" in text
