"""The server's clock - the ONLY source of attendance time (the phone's clock is never trusted).

Code must call `clock.now()` instead of datetime.now(), so tests can set the time.
"""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
