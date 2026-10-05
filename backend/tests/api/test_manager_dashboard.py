"""Phase 11: team attendance for managers (and HR), and CSV export.

World: mgr_a manages ann + ben (Lagos), mgr_b manages cal (Abuja). Mon-Sat 09:00-18:00.
"""

import csv
import io

from sqlalchemy import select

from app.models import AuditLog
from tests.api.attendance_helpers import (  # noqa: F401  (fixtures)
    approved_device,
    attempt,
    set_time,
)

OUTSIDE = (6.435750, 3.421900)


def team(client, world, who="mgr_a", **params):
    r = client.get("/api/v1/manager/attendance", headers=world.h(who), params={"date": "2026-10-05", **params})
    assert r.status_code == 200, r.text
    return r.json()


def rows_by_name(data):
    return {r["full_name"]: r for r in data["rows"]}


def test_manager_sees_only_their_team(client, world, set_time):
    data = team(client, world)
    assert sorted(rows_by_name(data)) == ["Ann", "Ben"]
    assert data["summary"]["total_employees"] == 2


def test_other_teams_employee_cannot_be_requested(client, world, set_time):
    assert team(client, world, employee_id=str(world.ids["cal"]))["rows"] == []


def test_hr_sees_everyone(client, world, set_time):
    assert team(client, world, "hr")["summary"]["total_employees"] == 6


def test_employee_has_no_access(client, world, set_time):
    r = client.get("/api/v1/manager/attendance", headers=world.h("ann"))
    assert r.status_code == 403


def test_a_working_day_in_progress(client, world, set_time):
    ann = approved_device(client, world, "ann")
    set_time(9, 5)
    attempt(client, world, "ann", ann)
    set_time(10, 0)
    data = team(client, world)
    rows = rows_by_name(data)
    assert rows["Ann"]["status"] == "PRESENT" and rows["Ann"]["checked_in_now"] is True
    assert rows["Ben"]["status"] == "NOT_CHECKED_IN"
    s = data["summary"]
    assert (s["present"], s["late"], s["not_checked_in"], s["absent"], s["checked_in_now"]) == (1, 0, 1, 0, 1)


def test_after_the_working_day_no_show_is_absent(client, world, set_time):
    set_time(18, 30)
    assert rows_by_name(team(client, world))["Ben"]["status"] == "ABSENT"


def test_late_arrival(client, world, set_time):
    ben = approved_device(client, world, "ben")
    set_time(9, 40)
    attempt(client, world, "ben", ben)
    data = team(client, world)
    assert rows_by_name(data)["Ben"]["status"] == "LATE"
    assert data["summary"]["late"] == 1 and data["summary"]["present"] == 1


def test_flagged_attendance_counts_as_suspicious_not_present(client, world, set_time):
    ann = approved_device(client, world, "ann")
    set_time(9, 0)
    attempt(client, world, "ann", ann, at=OUTSIDE)
    data = team(client, world)
    row = rows_by_name(data)["Ann"]
    assert row["status"] == "PENDING_REVIEW" and row["verification_status"] == "PENDING_REVIEW"
    assert data["summary"]["suspicious"] == 1 and data["summary"]["present"] == 0


def test_missing_checkout_shows_the_next_day(client, world, set_time):
    ann = approved_device(client, world, "ann")
    set_time(9, 0)
    attempt(client, world, "ann", ann)
    set_time(9, 0, day=(2026, 10, 6))  # Tuesday: Monday's session never closed
    data = team(client, world)
    row = rows_by_name(data)["Ann"]
    assert row["departure_status"] == "MISSING_CHECKOUT" and row["checked_in_now"] is False
    assert data["summary"]["missing_checkout"] == 1


def test_leave_holiday_and_day_off(client, world, set_time):
    client.post("/api/v1/leave", headers=world.h("hr"), json={
        "employee_id": str(world.ids["ben"]), "leave_type": "ANNUAL",
        "start_date": "2026-10-05", "end_date": "2026-10-05"})
    set_time(12, 0)
    data = team(client, world)
    assert rows_by_name(data)["Ben"]["status"] == "ON_LEAVE"
    assert rows_by_name(data)["Ben"]["note"] == "ANNUAL"
    assert data["summary"]["on_leave"] == 1

    client.post("/api/v1/holidays", headers=world.h("hr"), json={"holiday_date": "2026-10-06", "name": "X"})
    assert rows_by_name(team(client, world, date="2026-10-06"))["Ann"]["status"] == "HOLIDAY"
    assert rows_by_name(team(client, world, date="2026-10-04"))["Ann"]["status"] == "NON_WORKING_DAY"  # Sunday


def test_filters(client, world, set_time):
    ann = approved_device(client, world, "ann")
    set_time(9, 0)
    attempt(client, world, "ann", ann)
    set_time(12, 0)
    assert [r["full_name"] for r in team(client, world, status="PRESENT")["rows"]] == ["Ann"]
    assert [r["full_name"] for r in team(client, world, status="NOT_CHECKED_IN")["rows"]] == ["Ben"]
    assert [r["full_name"] for r in team(client, world, status="CHECKED_IN")["rows"]] == ["Ann"]
    assert [r["full_name"] for r in team(client, world, q="ben")["rows"]] == ["Ben"]
    hr = team(client, world, "hr", location_id=str(world.abuja_id))
    assert sorted(rows_by_name(hr)) == ["Cal", "Mgr_B"]
    r = client.get("/api/v1/manager/attendance", headers=world.h("mgr_a"), params={"status": "NONSENSE"})
    assert r.status_code == 422


def test_csv_export(client, world, set_time, test_session_factory):
    ann = approved_device(client, world, "ann")
    set_time(9, 5)
    attempt(client, world, "ann", ann)
    set_time(17, 0)
    attempt(client, world, "ann", ann, action="CHECK_OUT")
    r = client.get("/api/v1/manager/attendance/export.csv", headers=world.h("mgr_a"),
                   params={"date": "2026-10-05"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="attendance-2026-10-05.csv"' in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["Employee", "Employee ID", "Department"]
    ann_row = next(row for row in rows if row[0] == "Ann")
    assert ann_row[4:8] == ["09:05", "17:00", "7:55", "PRESENT"]
    assert ann_row[8] == "EARLY_DEPARTURE"
    with test_session_factory() as db:
        entry = db.scalar(select(AuditLog).where(AuditLog.action == "REPORT_EXPORTED",
                                                 AuditLog.actor_user_id.is_not(None)).order_by(AuditLog.seq.desc()))
        assert entry.actor_role == "MANAGER" and entry.new_value["rows"] == 2


def test_csv_export_blocks_spreadsheet_formulas(client, world, set_time):
    client.put(f"/api/v1/employees/{world.ids['ben']}", headers=world.h("hr"),
               json={"full_name": "=HYPERLINK(\"http://evil\")"})
    r = client.get("/api/v1/manager/attendance/export.csv", headers=world.h("mgr_a"), params={"date": "2026-10-05"})
    names = [row[0] for row in csv.reader(io.StringIO(r.content.decode("utf-8-sig")))]
    assert "'=HYPERLINK(\"http://evil\")" in names
