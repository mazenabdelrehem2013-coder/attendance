"""The exact text the phone signs (and hashes for Play Integrity) for every attendance request.

The phone app (Phase 10) MUST build this string in exactly the same way:

    v1|<action>|<challenge_id>|<nonce>|<client_request_id>|<device_id>|<lat 6 decimals>|
       <lng 6 decimals>|<accuracy 2 decimals>|<fix_age_ms>|<is_mock 0/1>|<device_time epoch ms>|<qr_token or empty>

(one line, no spaces). Binding all evidence into the signature means nothing in the request
can be changed after the phone signed it, and the Play Integrity token can't be reused for
a different request.
"""

import hashlib
from datetime import UTC, datetime, timedelta

from app.models.enums import AttendanceAction
from app.schemas.attendance import AttendanceSubmission


def canonical_payload(action: AttendanceAction, data: AttendanceSubmission) -> str:
    return "|".join(
        [
            "v1",
            action.value,
            str(data.challenge_id),
            data.nonce,
            str(data.client_request_id),
            str(data.device_id),
            f"{data.latitude:.6f}",
            f"{data.longitude:.6f}",
            f"{data.accuracy_m:.2f}",
            str(data.fix_age_ms),
            "1" if data.is_mock_location else "0",
            str(epoch_millis(data.device_time)),
            data.qr_token or "",
        ]
    )


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def epoch_millis(moment: datetime) -> int:
    """Whole milliseconds since 1970, computed exactly (no floating-point rounding), so the
    phone and the server always produce the same number."""
    return (moment - _EPOCH) // timedelta(milliseconds=1)


def request_hash(payload: str) -> str:
    """SHA-256 (hex) of the payload - the value the phone passes to Play Integrity."""
    return hashlib.sha256(payload.encode()).hexdigest()
