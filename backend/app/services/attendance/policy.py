"""Which security rules apply at a location: its own policy row, else the organization default,
else the built-in defaults below (decision 11.6: every failed check is FLAGGED)."""

import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendancePolicy
from app.models.enums import PolicyAction, VerificationMode


@dataclass(frozen=True)
class EffectivePolicy:
    verification_mode: VerificationMode = VerificationMode.GPS_ONLY
    on_mock_location: PolicyAction = PolicyAction.FLAG
    on_integrity_fail: PolicyAction = PolicyAction.FLAG
    on_poor_accuracy: PolicyAction = PolicyAction.FLAG
    on_stale_location: PolicyAction = PolicyAction.FLAG
    on_outside_geofence: PolicyAction = PolicyAction.FLAG
    on_impossible_travel: PolicyAction = PolicyAction.FLAG
    on_clock_skew: PolicyAction = PolicyAction.FLAG
    on_qr_fail: PolicyAction = PolicyAction.FLAG
    max_accuracy_m: int = 100
    max_fix_age_s: int = 60
    challenge_ttl_s: int = 90
    max_travel_speed_kmh: int = 200
    max_clock_skew_s: int = 300
    flagged_counts_before_review: bool = False

    def snapshot(self) -> dict:
        """Stored with every verification so later policy changes don't rewrite history."""
        return {k: (v.value if hasattr(v, "value") else v) for k, v in asdict(self).items()}


_FIELDS = list(EffectivePolicy.__dataclass_fields__)


def load_policy(db: Session, organization_id: uuid.UUID, location_id: uuid.UUID | None) -> EffectivePolicy:
    rows = db.scalars(
        select(AttendancePolicy).where(
            AttendancePolicy.organization_id == organization_id,
            (AttendancePolicy.location_id == location_id) | AttendancePolicy.location_id.is_(None),
        )
    ).all()
    # Prefer the location's own row over the organization default.
    row = next((r for r in rows if r.location_id is not None), None) or next(iter(rows), None)
    if row is None:
        return EffectivePolicy()
    return EffectivePolicy(**{name: getattr(row, name) for name in _FIELDS})
