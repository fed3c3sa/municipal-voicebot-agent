"""Integration tests against a real Postgres database.

Marked with @pytest.mark.integration and gated by the integration_db fixture,
which skips them when no database is available. They exercise the full path:
SQL schema -> repository -> MCP tools (via the in-memory FastMCP client).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastmcp import Client

from municipal_mcp.db import get_connection
from municipal_mcp.retrieval import hybrid_search
from municipal_mcp.server import build_server
from municipal_mcp.slots import generate_day_slots

pytestmark = pytest.mark.integration


def tool_text(result) -> str:
    data = getattr(result, "data", None)
    if isinstance(data, str):
        return data
    return result.content[0].text


def _first_open_slot_iso() -> str:
    day = date(2026, 6, 15)
    while not generate_day_slots(day):
        day += timedelta(days=1)
    return generate_day_slots(day)[0].isoformat()


def test_lexical_search_finds_document(integration_db):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO docs.documents (slug, title, category) VALUES (%s, %s, %s) RETURNING id",
            ("orari-test", "Orari uffici comunali", "Orari e contatti"),
        )
        document_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO docs.chunks (document_id, chunk_index, content) VALUES (%s, 0, %s)",
            (document_id, "L'ufficio anagrafe e' aperto dal lunedi al venerdi dalle 9 alle 13."),
        )
        conn.commit()

    # Lexical search ANDs the query terms; "uffici"/"aperti" exercise Italian
    # stemming against the document's "ufficio"/"aperto".
    results = hybrid_search("uffici anagrafe aperti", vector_enabled=False)
    assert any("anagrafe" in result.content.lower() for result in results)


async def test_appointment_full_flow(integration_db):
    start_iso = _first_open_slot_iso()
    async with Client(build_server()) as client:
        created = tool_text(
            await client.call_tool(
                "create_appointment",
                {
                    "name": "Maria",
                    "surname": "Rossi",
                    "phone": "0432999888",
                    "start_at": start_iso,
                    "reason": "rinnovo CIE",
                },
            )
        )
        assert "confermato" in created.lower()

        # Booking the same slot again must be rejected as occupied.
        conflict = tool_text(
            await client.call_tool(
                "create_appointment",
                {
                    "name": "Luigi",
                    "surname": "Bianchi",
                    "phone": "0432111222",
                    "start_at": start_iso,
                },
            )
        )
        assert "occupato" in conflict.lower()

        # The appointment can be found by phone.
        found = tool_text(await client.call_tool("check_appointments", {"phone": "0432999888"}))
        assert "Maria Rossi" in found

        # Cancelling without confirmation only asks for confirmation.
        appointment_id = _only_active_appointment_id()
        asked = tool_text(
            await client.call_tool("cancel_appointment", {"appointment_id": appointment_id})
        )
        assert "Vuole davvero cancellare" in asked

        # Confirmed cancellation removes the appointment and logs it.
        done = tool_text(
            await client.call_tool(
                "cancel_appointment", {"appointment_id": appointment_id, "confirm": True}
            )
        )
        assert "cancellato" in done.lower()

    assert _active_appointment_count() == 0
    assert _cancelled_appointment_count() == 1


def _only_active_appointment_id() -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM booking.appointments WHERE status = 'active' ORDER BY id LIMIT 1")
        return cur.fetchone()["id"]


def _active_appointment_count() -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM booking.appointments WHERE status = 'active'")
        return cur.fetchone()["n"]


def _cancelled_appointment_count() -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM booking.cancelled_appointments")
        return cur.fetchone()["n"]
