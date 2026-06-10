"""Appointment tools (create, check, edit, cancel) plus a slot helper.

Docstrings and parameters are in English (they form the tool schema the voice
agent reads); every returned message is in Italian. The mandatory create fields
are intentionally optional in the signature so the agent can call the tool with
partial information and be told, in Italian, exactly what is still missing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from .. import bookings
from ..bookings import OverlapError
from ..models import Appointment
from ..slots import (
    appointment_duration,
    format_datetime_it,
    format_time_it,
    generate_day_slots,
    parse_date,
    parse_datetime,
)


def _format_appointment(appointment: Appointment) -> str:
    parts = [
        f"Appuntamento numero {appointment.id}",
        f"{appointment.citizen_name} {appointment.citizen_surname}",
        f"telefono {appointment.phone}",
        format_datetime_it(appointment.start_at),
    ]
    if appointment.reason:
        parts.append(f"motivo: {appointment.reason}")
    return ", ".join(parts)


def _slots_message(day_label: str, free_slots: list[datetime]) -> str:
    if not free_slots:
        return (
            f"Per {day_label} non ci sono orari disponibili "
            "(l'ufficio potrebbe essere chiuso o gli orari sono gia' tutti occupati)."
        )
    orari = ", ".join(format_time_it(slot) for slot in free_slots)
    return f"Gli orari disponibili per {day_label} sono: {orari}."


def register(mcp) -> None:
    """Register the appointment tools on the given FastMCP server."""

    @mcp.tool
    def get_available_slots(
        date: Annotated[str, Field(description="The day to check, in ISO format YYYY-MM-DD.")],
    ) -> str:
        """List the free appointment slots for a given day.

        Use this to propose concrete times to the citizen before booking.
        """
        try:
            day = parse_date(date)
        except ValueError:
            return "La data non e' valida. Usare il formato anno-mese-giorno, ad esempio 2026-06-15."
        free = bookings.find_free_slots(day)
        return _slots_message(f"il {day.day}/{day.month}/{day.year}", free)

    @mcp.tool
    def create_appointment(
        name: Annotated[str | None, Field(description="Citizen first name.")] = None,
        surname: Annotated[str | None, Field(description="Citizen surname.")] = None,
        phone: Annotated[str | None, Field(description="Citizen phone number.")] = None,
        start_at: Annotated[
            str | None,
            Field(description="Appointment start, ISO format YYYY-MM-DDTHH:MM (local time)."),
        ] = None,
        reason: Annotated[str | None, Field(description="Optional reason for the appointment.")] = None,
    ) -> str:
        """Create an appointment on the municipal calendar.

        Mandatory data: name, surname, phone and start time. If any is missing,
        the tool replies (in Italian) listing what is still needed, so the agent
        can ask the citizen. The appointment must fall on an available slot and
        must not overlap an existing one.
        """
        missing = []
        if not name:
            missing.append("il nome")
        if not surname:
            missing.append("il cognome")
        if not phone:
            missing.append("il numero di telefono")
        if not start_at:
            missing.append("la data e l'ora dell'appuntamento")
        if missing:
            return "Per fissare l'appuntamento mi servono ancora: " + ", ".join(missing) + "."

        try:
            start = parse_datetime(start_at)
        except ValueError:
            return (
                "Non ho capito la data e l'ora. Usare il formato "
                "anno-mese-giorno ora:minuti, ad esempio 2026-06-15T09:30."
            )

        day = start.date()
        if start not in generate_day_slots(day):
            free = bookings.find_free_slots(day)
            return (
                f"L'orario richiesto non e' disponibile. "
                f"{_slots_message(f'il {day.day}/{day.month}/{day.year}', free)}"
            )

        try:
            appointment = bookings.create_appointment(
                name=name, surname=surname, phone=phone, start_at=start, reason=reason
            )
        except OverlapError:
            free = bookings.find_free_slots(day)
            return (
                f"Quell'orario e' gia' occupato. "
                f"{_slots_message(f'il {day.day}/{day.month}/{day.year}', free)}"
            )

        return (
            f"Appuntamento confermato per {format_datetime_it(appointment.start_at)} "
            f"a nome di {appointment.citizen_name} {appointment.citizen_surname}. "
            f"Il numero dell'appuntamento e' {appointment.id}. "
            f"La durata prevista e' di {appointment_duration()} minuti."
        )

    @mcp.tool
    def check_appointments(
        phone: Annotated[str | None, Field(description="Filter by citizen phone number.")] = None,
        surname: Annotated[str | None, Field(description="Filter by citizen surname.")] = None,
        date: Annotated[str | None, Field(description="Filter by day, ISO format YYYY-MM-DD.")] = None,
    ) -> str:
        """Look up existing appointments by phone, surname, or day.

        Use this to check an appointment's details when the citizen asks.
        """
        if not phone and not surname and not date:
            return (
                "Per cercare un appuntamento mi serve almeno il numero di telefono, "
                "il cognome oppure la data."
            )

        day = None
        if date:
            try:
                day = parse_date(date)
            except ValueError:
                return "La data non e' valida. Usare il formato anno-mese-giorno, ad esempio 2026-06-15."

        results = bookings.find_appointments(phone=phone, surname=surname, day=day)
        if not results:
            return "Non ho trovato appuntamenti corrispondenti alla ricerca."

        lines = ["Ho trovato questi appuntamenti:"]
        lines.extend(f"- {_format_appointment(appointment)}" for appointment in results)
        return "\n".join(lines)

    @mcp.tool
    def edit_appointment(
        appointment_id: Annotated[int, Field(description="The id of the appointment to edit.")],
        start_at: Annotated[
            str | None,
            Field(description="New start time, ISO format YYYY-MM-DDTHH:MM (local time)."),
        ] = None,
        name: Annotated[str | None, Field(description="New first name.")] = None,
        surname: Annotated[str | None, Field(description="New surname.")] = None,
        phone: Annotated[str | None, Field(description="New phone number.")] = None,
        reason: Annotated[str | None, Field(description="New reason.")] = None,
    ) -> str:
        """Edit an existing appointment. A new time must stay free of overlaps."""
        new_start = None
        if start_at:
            try:
                new_start = parse_datetime(start_at)
            except ValueError:
                return (
                    "Non ho capito la nuova data e ora. Usare il formato "
                    "anno-mese-giorno ora:minuti, ad esempio 2026-06-15T09:30."
                )
            day = new_start.date()
            if new_start not in generate_day_slots(day):
                free = bookings.find_free_slots(day)
                return (
                    f"Il nuovo orario non e' disponibile. "
                    f"{_slots_message(f'il {day.day}/{day.month}/{day.year}', free)}"
                )

        try:
            updated = bookings.update_appointment(
                appointment_id,
                start_at=new_start,
                name=name,
                surname=surname,
                phone=phone,
                reason=reason,
            )
        except OverlapError:
            return "Il nuovo orario si sovrappone a un altro appuntamento. Scegliere un orario diverso."

        if updated is None:
            return f"Non ho trovato l'appuntamento numero {appointment_id}."
        return f"Appuntamento aggiornato. {_format_appointment(updated)}."

    @mcp.tool
    def cancel_appointment(
        appointment_id: Annotated[int, Field(description="The id of the appointment to cancel.")],
        confirm: Annotated[
            bool,
            Field(description="Must be true to actually cancel. If false, asks for confirmation first."),
        ] = False,
    ) -> str:
        """Cancel an appointment, asking for confirmation first.

        When confirm is false, returns the appointment details and asks the
        citizen to confirm. When confirm is true, the appointment is logged in
        the cancellation register (so no information is lost) and then removed.
        """
        appointment = bookings.get_appointment(appointment_id)
        if appointment is None or appointment.status != "active":
            return f"Non ho trovato un appuntamento attivo con il numero {appointment_id}."

        if not confirm:
            return (
                f"Vuole davvero cancellare questo appuntamento? "
                f"{_format_appointment(appointment)}. "
                "Per procedere confermi la cancellazione."
            )

        cancelled = bookings.cancel_appointment(appointment_id)
        if cancelled is None:
            return f"Non ho trovato un appuntamento attivo con il numero {appointment_id}."
        return (
            f"Appuntamento numero {cancelled.id} cancellato. "
            "La cancellazione e' stata registrata."
        )
