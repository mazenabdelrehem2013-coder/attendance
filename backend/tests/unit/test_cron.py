"""Phase 15 building blocks: schedule times and schedule wording."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.schemas.schedules import ScheduleIn
from app.services.cron import Cron, CronError
from app.services.report_schedules import describe, to_cron

LAGOS = ZoneInfo("Africa/Lagos")


def at(day, hh, mm=0):
    return datetime(2026, 10, day, hh, mm, tzinfo=LAGOS)  # 5 Oct 2026 is a Monday


def test_daily_monday_to_saturday():
    cron = Cron.parse("0 8 * * 1-6")
    assert cron.previous(at(5, 8, 0)) == at(5, 8)  # exactly on time counts
    assert cron.previous(at(5, 7, 59)) == at(3, 8)  # Monday early -> Saturday
    assert cron.next(at(10, 9)) == at(12, 8)  # Saturday after 08:00 -> skips Sunday
    assert not cron.day_matches(at(11, 0).date())


def test_weekly_and_monthly():
    assert Cron.parse("30 7 * * 1").next(at(5, 7, 30)) == at(12, 7, 30)
    monthly = Cron.parse("0 6 1 * *")
    assert monthly.previous(at(5, 12)) == at(1, 6)
    assert monthly.next(at(5, 12)) == datetime(2026, 11, 1, 6, tzinfo=LAGOS)


def test_lists_steps_and_sunday_as_7():
    cron = Cron.parse("*/30 9,17 * * 7")
    assert cron.previous(at(11, 17, 45)) == at(11, 17, 30)
    assert cron.next(at(11, 9, 0)) == at(11, 9, 30)


def test_day_of_month_or_weekday():
    cron = Cron.parse("0 8 15 * 1")  # standard cron: the 15th OR any Monday
    assert cron.day_matches(at(5, 0).date()) and cron.day_matches(at(15, 0).date())
    assert not cron.day_matches(at(14, 0).date())


@pytest.mark.parametrize("bad", ["", "0 8 * *", "60 8 * * *", "0 24 * * *", "0 8 32 * *", "0 8 * * 8", "a b c d e"])
def test_invalid_expressions(bad):
    with pytest.raises(CronError):
        Cron.parse(bad)


def test_schedule_form_to_cron_and_wording():
    daily = ScheduleIn(name="d", report="daily", frequency="daily", time="07:45", days=[0, 1, 2, 3, 4, 5])
    assert to_cron(daily) == "45 7 * * 1,2,3,4,5,6" and describe(daily) == "Monday to Saturday at 07:45"
    weekly = ScheduleIn(name="w", report="weekly", frequency="weekly", time="08:00", weekday=6)
    assert to_cron(weekly) == "0 8 * * 0" and describe(weekly) == "Every Sunday at 08:00"
    monthly = ScheduleIn(name="m", report="late", frequency="monthly", time="06:30", day_of_month=2)
    assert to_cron(monthly) == "30 6 2 * *" and describe(monthly) == "Monthly on day 2 at 06:30"
    with pytest.raises(ValueError):
        ScheduleIn(name="x", report="weekly", frequency="daily")
    with pytest.raises(ValueError):
        ScheduleIn(name="x", report="late", frequency="daily", recipient_roles=[])
