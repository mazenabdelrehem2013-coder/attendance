"""Phase 13: end-of-day job and reports, checked against a hand-made week.

Week Mon 5 - Sun 11 Oct 2026, schedule Mon-Sat 09:00-18:00, grace 15 min.
  ann: Mon 09:05-17:00 | Tue 09:30-18:00 | Wed nothing | Thu annual leave | Fri holiday
       | Sat 09:00, never checked out | Sun day off
  ben: nothing all week
Reports are run on Monday 12 Oct.
"""

from datetime import date

import pytest

from app.jobs.close_day import close_day
from tests.api.attendance_helpers import approved_device, attempt, set_time  # noqa: F401

WEEK = {"from": "2026-10-05", "to": "2026-10-11"}


def on(day: int):
    return (2026, 10, day)


@pytest.fixture
def week(client, world, set_time, test_session_factory):
    ann = approved_device(client, world, "ann")
    hr = world.h("hr")
    client.post("/api/v1/leave", headers=hr, json={"employee_id": str(world.ids["ann"]), "leave_type": "ANNUAL",
                                                   "start_date": "2026-10-08", "end_date": "2026-10-08"})
    client.post("/api/v1/holidays", headers=hr, json={"holiday_date": "2026-10-09", "name": "Company Day"})

    for day, check_in, check_out in [(5, (9, 5), (17, 0)), (6, (9, 30), (18, 0)), (10, (9, 0), None)]:
        set_time(*check_in, day=on(day))
        assert attempt(client, world, "ann", ann).json()["result"] == "ACCEPTED"
        if check_out:
            set_time(*check_out, day=on(day))
            assert attempt(client, world, "ann", ann, action="CHECK_OUT").json()["result"] == "ACCEPTED"

    set_time(3, 0, day=on(12))  # Monday night job for the whole week
    with test_session_factory() as db:
        for day in range(5, 12):
            close_day(db, world.org_id, date(2026, 10, day))
    set_time(10, 0, day=on(12))
    return world


def get(client, world, path, who="hr", **params):
    r = client.get(f"/api/v1/reports/{path}", headers=world.h(who), params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --- End-of-day job -------------------------------------------------------------------------


def test_close_day_marks_absences_and_missing_checkouts(client, world, set_time, test_session_factory):
    ann = approved_device(client, world, "ann")
    set_time(9, 0, day=on(5))
    attempt(client, world, "ann", ann)  # never checks out
    set_time(2, 0, day=on(6))
    with test_session_factory() as db:
        result = close_day(db, world.org_id, date(2026, 10, 5))
    assert result.missing_checkouts == 1
    assert result.absences == 5  # hr, mgr_a, mgr_b, ben, cal - everyone except ann
    with test_session_factory() as db:
        again = close_day(db, world.org_id, date(2026, 10, 5))  # safe to run twice
    assert (again.missing_checkouts, again.absences) == (0, 0)

    team = client.get("/api/v1/manager/attendance", headers=world.h("mgr_a"), params={"date": "2026-10-05"}).json()
    rows = {r["full_name"]: r for r in team["rows"]}
    assert rows["Ann"]["departure_status"] == "MISSING_CHECKOUT" and rows["Ann"]["worked_minutes"] == 0
    assert rows["Ben"]["status"] == "ABSENT"


def test_close_day_skips_sundays_leave_and_holidays(client, world, set_time, test_session_factory):
    client.post("/api/v1/leave", headers=world.h("hr"), json={"employee_id": str(world.ids["ben"]),
                "leave_type": "SICK", "start_date": "2026-10-06", "end_date": "2026-10-06"})
    set_time(2, 0, day=on(12))
    with test_session_factory() as db:
        assert close_day(db, world.org_id, date(2026, 10, 4)).absences == 0  # Sunday
        assert close_day(db, world.org_id, date(2026, 10, 6)).absences == 5  # ben on leave


def test_close_day_refuses_a_day_that_is_not_over(world, set_time, test_session_factory):
    set_time(20, 0, day=on(5))
    with test_session_factory() as db, pytest.raises(ValueError):
        close_day(db, world.org_id, date(2026, 10, 5))


# --- Period (weekly / monthly) --------------------------------------------------------------


def test_weekly_figures_match_the_hand_calculation(client, week):
    data = get(client, week, "weekly", date="2026-10-07")
    assert (data["date_from"], data["date_to"]) == ("2026-10-05", "2026-10-11")
    ann = next(r for r in data["rows"] if r["employee"] == "Ann")
    assert ann["working_days"] == 4  # Mon, Tue, Wed, Sat
    assert ann["present_days"] == 3
    assert ann["late_days"] == 1
    assert ann["absent_days"] == 1
    assert ann["leave_days"] == 1 and ann["holiday_days"] == 1
    assert ann["early_departure_days"] == 1  # Monday 17:00
    assert ann["missing_checkout_days"] == 1  # Saturday
    assert ann["average_check_in"] == "09:12"  # (09:05 + 09:30 + 09:00) / 3
    assert ann["average_check_out"] == "17:30"
    assert ann["total_worked_minutes"] == 475 + 510
    assert ann["attendance_rate"] == 0.75

    ben = next(r for r in data["rows"] if r["employee"] == "Ben")
    assert (ben["working_days"], ben["absent_days"], ben["attendance_rate"]) == (5, 5, 0.0)


def test_group_totals(client, week):
    data = get(client, week, "weekly", date="2026-10-07")
    lagos = next(g for g in data["by_location"] if g["name"] == "Lagos")
    assert lagos["employees"] == 4  # hr, mgr_a, ann, ben
    assert lagos["present_days"] == 3
    by_manager = {g["name"]: g for g in data["by_manager"]}
    assert by_manager["Mgr_A"]["employees"] == 2


def test_monthly_report_up_to_today(client, week):
    data = get(client, week, "monthly", month="2026-10")
    assert (data["date_from"], data["date_to"]) == ("2026-10-01", "2026-10-31")
    ann = next(r for r in data["rows"] if r["employee"] == "Ann")
    # 1-11 Oct: 1 Oct Thu, 2 Fri, 3 Sat are working days with no attendance -> absent too.
    assert ann["present_days"] == 3 and ann["absent_days"] == 4
    # 1,2,3,5,6,7,10 Oct. Today (12th) is still running and Ann hasn't checked in: not counted yet.
    assert ann["working_days"] == 7


def test_manager_report_contains_only_their_team(client, week):
    data = get(client, week, "weekly", who="mgr_b", date="2026-10-07")
    assert [r["employee"] for r in data["rows"]] == ["Cal"]


def test_filters(client, week):
    data = get(client, week, "period", employee_id=str(week.ids["ann"]), **WEEK)
    assert [r["employee"] for r in data["rows"]] == ["Ann"]
    data = get(client, week, "period", location_id=str(week.abuja_id), **WEEK)
    assert sorted(r["employee"] for r in data["rows"]) == ["Cal", "Mgr_B"]


# --- Daily and lists ------------------------------------------------------------------------


def test_daily_report(client, week):
    data = get(client, week, "daily", date="2026-10-06")
    ann = next(r for r in data["rows"] if r["employee"] == "Ann")
    assert (ann["check_in"], ann["check_out"], ann["worked_minutes"], ann["status"]) == ("09:30", "18:00", 510, "LATE")
    assert ann["manager"] == "Mgr_A"
    assert data["totals"]["late"] == 1


def test_late_list(client, week):
    rows = get(client, week, "late", **WEEK)["rows"]
    assert [(r["employee"], r["date"], r["minutes"]) for r in rows] == [("Ann", "2026-10-06", 30)]


def test_absence_list(client, week):
    rows = get(client, week, "absence", employee_id=str(week.ids["ann"]), **WEEK)["rows"]
    assert [r["date"] for r in rows] == ["2026-10-07"]
    ben = get(client, week, "absence", employee_id=str(week.ids["ben"]), **WEEK)["rows"]
    assert [r["date"] for r in ben] == ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-10"]


def test_suspicious_list(client, world, set_time):
    ann = approved_device(client, world, "ann")
    set_time(9, 0, day=on(5))
    attempt(client, world, "ann", ann, is_mock_location=True)
    set_time(10, 0, day=on(12))
    rows = get(client, world, "suspicious", **WEEK)["rows"]
    assert len(rows) == 1
    assert "Fake-GPS app detected" in rows[0]["detail"] and "waiting for HR" in rows[0]["detail"]


def test_reports_need_manager_or_hr(client, world):
    assert client.get("/api/v1/reports/daily", headers=world.h("ann")).status_code == 403


def test_period_limit(client, world):
    r = client.get("/api/v1/reports/period", headers=world.h("hr"), params={"from": "2024-01-01", "to": "2026-10-05"})
    assert r.status_code == 422
