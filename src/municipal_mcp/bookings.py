"""Appointment data access (single shared municipal calendar).

This module owns every SQL statement that touches the booking schema and
raises a typed OverlapError when a time clash is detected. The no-overlap rule
is ultimately guaranteed by the database exclusion constraint; we simply catch
the violation and turn it into a clean exception for the tools to format.
"""

from __future__ import annotations

from datetime import date, datetime

from psycopg import errors as pg_errors

from .db import get_connection
from .models import Appointment
from .slots import add_duration, appointment_duration, day_bounds, generate_day_slots, intervals_overlap


class OverlapError(Exception):
    """Raised when a requested appointment time clashes with an existing one."""


_APPOINTMENT_COLUMNS = (
    "id, citizen_name, citizen_surname, phone, reason, "
    "start_at, end_at, duration_minutes, status"
)


def _row_to_appointment(row: dict) -> Appointment:
    return Appointment(
        id=row["id"],
        citizen_name=row["citizen_name"],
        citizen_surname=row["citizen_surname"],
        phone=row["phone"],
        reason=row["reason"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        duration_minutes=row["duration_minutes"],
        status=row["status"],
    )


def create_appointment(
    *,
    name: str,
    surname: str,
    phone: str,
    start_at: datetime,
    reason: str | None = None,
    duration_minutes: int | None = None,
) -> Appointment:
    """Insert a new appointment. Raises OverlapError on a time clash."""
    duration = appointment_duration() if duration_minutes is None else duration_minutes
    end_at = add_duration(start_at, duration)

    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                f"""
                INSERT INTO booking.appointments
                    (citizen_name, citizen_surname, phone, reason,
                     start_at, end_at, duration_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING {_APPOINTMENT_COLUMNS}
                """,
                (name, surname, phone, reason, start_at, end_at, duration),
            )
        except pg_errors.ExclusionViolation as exc:
            conn.rollback()
            raise OverlapError("L'orario richiesto si sovrappone a un altro appuntamento.") from exc
        row = cur.fetchone()
        conn.commit()
    return _row_to_appointment(row)


def get_appointment(appointment_id: int) -> Appointment | None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_APPOINTMENT_COLUMNS} FROM booking.appointments WHERE id = %s",
            (appointment_id,),
        )
        row = cur.fetchone()
    return _row_to_appointment(row) if row else None


def find_appointments(
    *,
    phone: str | None = None,
    surname: str | None = None,
    day: date | None = None,
) -> list[Appointment]:
    """Find active appointments matching any of the given filters."""
    clauses = ["status = 'active'"]
    params: dict[str, object] = {}
    if phone:
        clauses.append("phone = %(phone)s")
        params["phone"] = phone
    if surname:
        clauses.append("lower(citizen_surname) = lower(%(surname)s)")
        params["surname"] = surname
    if day:
        start, end = day_bounds(day)
        clauses.append("start_at >= %(day_start)s AND start_at < %(day_end)s")
        params["day_start"] = start
        params["day_end"] = end

    sql = (
        f"SELECT {_APPOINTMENT_COLUMNS} FROM booking.appointments "
        f"WHERE {' AND '.join(clauses)} ORDER BY start_at"
    )
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [_row_to_appointment(row) for row in rows]


def find_free_slots(day: date) -> list[datetime]:
    """Return the office-hours slots on `day` that are not already booked."""
    candidates = generate_day_slots(day)
    if not candidates:
        return []

    start, end = day_bounds(day)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT start_at, end_at FROM booking.appointments
            WHERE status = 'active' AND start_at < %(day_end)s AND end_at > %(day_start)s
            """,
            {"day_start": start, "day_end": end},
        )
        busy = [(row["start_at"], row["end_at"]) for row in cur.fetchall()]

    free: list[datetime] = []
    for slot in candidates:
        slot_end = add_duration(slot)
        if not any(intervals_overlap(slot, slot_end, busy_start, busy_end) for busy_start, busy_end in busy):
            free.append(slot)
    return free


def update_appointment(
    appointment_id: int,
    *,
    start_at: datetime | None = None,
    name: str | None = None,
    surname: str | None = None,
    phone: str | None = None,
    reason: str | None = None,
    duration_minutes: int | None = None,
) -> Appointment | None:
    """Update an appointment in place. Raises OverlapError on a time clash.

    Returns None if the appointment does not exist.
    """
    current = get_appointment(appointment_id)
    if current is None:
        return None

    new_start = start_at if start_at is not None else current.start_at
    new_duration = duration_minutes if duration_minutes is not None else current.duration_minutes
    new_end = add_duration(new_start, new_duration)

    fields = {
        "citizen_name": name if name is not None else current.citizen_name,
        "citizen_surname": surname if surname is not None else current.citizen_surname,
        "phone": phone if phone is not None else current.phone,
        "reason": reason if reason is not None else current.reason,
        "start_at": new_start,
        "end_at": new_end,
        "duration_minutes": new_duration,
    }

    with get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(
                f"""
                UPDATE booking.appointments
                SET citizen_name = %(citizen_name)s,
                    citizen_surname = %(citizen_surname)s,
                    phone = %(phone)s,
                    reason = %(reason)s,
                    start_at = %(start_at)s,
                    end_at = %(end_at)s,
                    duration_minutes = %(duration_minutes)s,
                    updated_at = now()
                WHERE id = %(id)s
                RETURNING {_APPOINTMENT_COLUMNS}
                """,
                {**fields, "id": appointment_id},
            )
        except pg_errors.ExclusionViolation as exc:
            conn.rollback()
            raise OverlapError("Il nuovo orario si sovrappone a un altro appuntamento.") from exc
        row = cur.fetchone()
        conn.commit()
    return _row_to_appointment(row)


def cancel_appointment(
    appointment_id: int,
    *,
    cancelled_by: str = "voicebot",
    note: str | None = None,
) -> Appointment | None:
    """Move an active appointment into the cancellation log and delete it.

    Returns the cancelled appointment, or None if it did not exist. Copying the
    row into booking.cancelled_appointments before deletion ensures the operator
    never loses information about a removed booking.
    """
    appointment = get_appointment(appointment_id)
    if appointment is None or appointment.status != "active":
        return None

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO booking.cancelled_appointments
                (original_appointment_id, citizen_name, citizen_surname, phone,
                 reason, start_at, end_at, cancelled_by, cancellation_note)
            SELECT id, citizen_name, citizen_surname, phone,
                   reason, start_at, end_at, %(cancelled_by)s, %(note)s
            FROM booking.appointments
            WHERE id = %(id)s
            """,
            {"id": appointment_id, "cancelled_by": cancelled_by, "note": note},
        )
        cur.execute("DELETE FROM booking.appointments WHERE id = %(id)s", {"id": appointment_id})
        conn.commit()
    return appointment
