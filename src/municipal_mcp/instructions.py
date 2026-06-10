"""The instructions string handed to the agent when it connects and loads the tools.

The MCP initialize response carries an `instructions` field that the connecting
voice agent reads alongside the tool list. We rebuild it on every new connection
with the current date (in the booking timezone) so the agent always knows what
"today" is and can turn the relative dates a citizen mentions ("domani", "lunedi
prossimo") into the ISO dates the appointment tools expect.
"""

from __future__ import annotations

from datetime import datetime

from .slots import get_timezone

_WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]


def server_instructions() -> str:
    """Build the connection instructions, stamped with the current date."""
    now = datetime.now(get_timezone())
    return (
        f"Today is {now:%Y-%m-%d} ({_WEEKDAYS[now.weekday()]}), "
        f"timezone {now.tzname()}. Use this as the reference for \"today\" when "
        "the citizen mentions relative dates such as \"domani\" or \"lunedi "
        "prossimo\", and convert them to ISO (YYYY-MM-DD, or YYYY-MM-DDTHH:MM "
        "for a start time) before calling the appointment tools."
    )
