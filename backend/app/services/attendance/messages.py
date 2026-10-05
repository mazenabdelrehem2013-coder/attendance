"""What the employee is told. Deliberately general: it never says WHICH security check fired,
so nobody learns how to get around them (spec section 27). HR sees the real reason."""

MESSAGES = {
    "CHECK_IN_OK": "Check-in successful.",
    "CHECK_OUT_OK": "Check-out successful.",
    "PENDING_REVIEW": "Your attendance was recorded and is waiting for HR review.",
    "OUTSIDE_LOCATION": "You appear to be outside your assigned work location.",
    "VERIFICATION_FAILED": "We couldn't verify this attendance. Please contact HR.",
    "WEAK_SIGNAL": "Your location signal is weak. Move to an open area or near a window and try again.",
    "ALREADY_CHECKED_IN": "You are already checked in. Check out first.",
    "NOT_CHECKED_IN": "You are not checked in.",
    "NO_ASSIGNED_LOCATION": "You have no active work location. Please contact HR.",
    "REQUEST_EXPIRED": "This request expired. Please try again.",
}


def employee_message(code: str | None) -> str:
    return MESSAGES.get(code or "", MESSAGES["VERIFICATION_FAILED"])
