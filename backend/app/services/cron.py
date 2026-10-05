"""Tiny cron-expression reader ("minute hour day-of-month month day-of-week").

Supports what the scheduled reports use: numbers, `*`, lists (1,3,5), ranges (1-6) and steps
(*/15). Day-of-week: 0 or 7 = Sunday, 1 = Monday ... 6 = Saturday. As in standard cron, when
both day-of-month and day-of-week are restricted, a day matching EITHER one counts.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta


class CronError(ValueError):
    pass


_LIMITS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def _field(text: str, low: int, high: int) -> set[int] | None:
    """None = '*' (any value)."""
    if text == "*":
        return None
    values: set[int] = set()
    for part in text.split(","):
        rng, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if rng == "*":
            start, end = low, high
        elif "-" in rng:
            a, b = rng.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(rng)
        if not (low <= start <= end <= high) or step < 1:
            raise CronError(f"'{part}' is outside {low}-{high}")
        values.update(range(start, end + 1, step))
    return values


@dataclass(frozen=True)
class Cron:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int] | None
    months: frozenset[int] | None
    weekdays: frozenset[int] | None  # cron numbering, Sunday = 0

    @classmethod
    def parse(cls, expression: str) -> "Cron":
        parts = expression.split()
        if len(parts) != 5:
            raise CronError("A schedule needs 5 parts: minute hour day month weekday")
        try:
            fields = [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _LIMITS)]
        except ValueError as e:
            raise CronError(str(e)) from None
        minutes, hours, days, months, weekdays = fields
        if weekdays is not None:
            weekdays = {0 if d == 7 else d for d in weekdays}
        return cls(
            frozenset(minutes if minutes is not None else range(60)),
            frozenset(hours if hours is not None else range(24)),
            frozenset(days) if days is not None else None,
            frozenset(months) if months is not None else None,
            frozenset(weekdays) if weekdays is not None else None,
        )

    def day_matches(self, d: date) -> bool:
        if self.months is not None and d.month not in self.months:
            return False
        dom_ok = self.days is None or d.day in self.days
        dow_ok = self.weekdays is None or (d.weekday() + 1) % 7 in self.weekdays
        if self.days is not None and self.weekdays is not None:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def _times(self) -> list[tuple[int, int]]:
        return sorted((h, m) for h in self.hours for m in self.minutes)

    def previous(self, moment: datetime, max_days: int = 400) -> datetime | None:
        """Latest scheduled time at or before `moment` (same timezone as `moment`)."""
        times = self._times()
        for back in range(max_days):
            d = moment.date() - timedelta(days=back)
            if not self.day_matches(d):
                continue
            for h, m in reversed(times):
                candidate = moment.replace(year=d.year, month=d.month, day=d.day, hour=h, minute=m,
                                           second=0, microsecond=0)
                if candidate <= moment:
                    return candidate
        return None

    def next(self, moment: datetime, max_days: int = 400) -> datetime | None:
        """First scheduled time strictly after `moment`."""
        times = self._times()
        for ahead in range(max_days):
            d = moment.date() + timedelta(days=ahead)
            if not self.day_matches(d):
                continue
            for h, m in times:
                candidate = moment.replace(year=d.year, month=d.month, day=d.day, hour=h, minute=m,
                                           second=0, microsecond=0)
                if candidate > moment:
                    return candidate
        return None
