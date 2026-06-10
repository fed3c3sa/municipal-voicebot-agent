"""Shared Pydantic data models.

These are the schema objects passed between the data layer and the tools. Tool
input parameters are declared inline on the tool functions (idiomatic FastMCP);
configuration lives in config.py. Everything else that is a structured data
object belongs here.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class SearchResult(BaseModel):
    """One retrieved chunk plus its parent document metadata."""

    score: float
    content: str
    heading_path: str | None
    chunk_index: int
    full_text: str | None
    title: str
    category: str | None
    source_url: str | None
    doc_date: date | None


class Appointment(BaseModel):
    """An appointment on the shared municipal calendar."""

    id: int
    citizen_name: str
    citizen_surname: str
    phone: str
    reason: str | None
    start_at: datetime
    end_at: datetime
    duration_minutes: int
    status: str
