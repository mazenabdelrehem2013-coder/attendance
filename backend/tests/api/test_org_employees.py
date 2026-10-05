"""Phase 5: organization structure, employees, manager scoping, audit logging."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.api.conftest import PASSWORD
from tests.api.world import build_world


def _audits(session_factory, object_id, action):
    with session_factory() as db:
        return db.scalars(
            select(AuditLog).where(AuditLog.object_id == str(object_id), AuditLog.action == action)
        ).all()


NEW_LOCATION = {"name": "Uyo Office", "code": "uyo", "latitude": 5.0377, "longitude": 7.9128,
                "radius_m": 150, "timezone": "Africa/Lagos"}


# --- Locations ------------------------------------------------------------------------------


def test_hr_creates_and_updates_location_with_audit(client, world, test_session_factory):
    r = client.post("/api/v1/locations", headers=world.h("hr"),
                    json={**NEW_LOCATION, "branch_id": str(world.branch_id)})
    assert r.status_code == 201, r.text
    loc = r.json()
    assert loc["code"] == "UYO" and loc["radius_m"] == 150
    assert len(_audits(test_session_factory, loc["id"], "LOCATION_CREATED")) == 1

    r = client.put(f"/api/v1/locations/{loc['id']}", headers=world.h("hr"), json={"radius_m": 300})
    assert r.status_code == 200 and r.json()["radius_m"] == 300
    (entry,) = _audits(test_session_factory, loc["id"], "LOCATION_UPDATED")
    assert entry.old_value == {"radius_m": 150} and entry.new_value == {"radius_m": 300}
    assert entry.actor_role == "HR"


@pytest.mark.parametrize("who", ["ann", "mgr_a"])
def test_employees_and_managers_cannot_change_locations(client, world, who):
    body = {**NEW_LOCATION, "branch_id": str(world.branch_id)}
    assert client.post("/api/v1/locations", headers=world.h(who), json=body).status_code == 403
    r = client.put(f"/api/v1/locations/{world.lagos_id}", headers=world.h(who), json={"radius_m": 5000})
    assert r.status_code == 403


@pytest.mark.parametrize(
    "bad",
    [{"latitude": 95}, {"longitude": -200}, {"radius_m": 5}, {"timezone": "Mars/Base"}, {"code": "bad code!"}],
)
def test_location_input_is_validated(client, world, bad):
    body = {**NEW_LOCATION, "branch_id": str(world.branch_id), **bad}
    assert client.post("/api/v1/locations", headers=world.h("hr"), json=body).status_code == 422


def test_duplicate_location_code_is_refused(client, world):
    body = {**NEW_LOCATION, "code": "LOS", "branch_id": str(world.branch_id)}
    assert client.post("/api/v1/locations", headers=world.h("hr"), json=body).status_code == 409


def test_required_field_cannot_be_set_to_null(client, world):
    r = client.put(f"/api/v1/locations/{world.lagos_id}", headers=world.h("hr"), json={"name": None})
    assert r.status_code == 422


def test_disable_location_hides_it_from_default_list(client, world):
    client.put(f"/api/v1/locations/{world.abuja_id}", headers=world.h("hr"), json={"is_active": False})
    names = [l["name"] for l in client.get("/api/v1/locations", headers=world.h("hr")).json()]
    assert names == ["Lagos"]
    names = [l["name"] for l in client.get("/api/v1/locations?include_inactive=true", headers=world.h("hr")).json()]
    assert names == ["Abuja", "Lagos"]


def test_employee_sees_only_assigned_locations(client, world):
    names = [l["name"] for l in client.get("/api/v1/locations", headers=world.h("cal")).json()]
    assert names == ["Abuja"]


def test_other_organizations_data_is_invisible(client, world, test_session_factory):
    other = build_world(test_session_factory, client)
    assert client.get(f"/api/v1/locations/{other.lagos_id}", headers=world.h("hr")).status_code == 404
    assert client.get(f"/api/v1/employees/{other.ids['ann']}", headers=world.h("hr")).status_code == 404
    r = client.put(f"/api/v1/locations/{other.lagos_id}", headers=world.h("hr"), json={"radius_m": 999})
    assert r.status_code == 404
    listed = client.get("/api/v1/employees?page_size=200", headers=world.h("hr")).json()["items"]
    assert not {e["id"] for e in listed} & {str(i) for i in other.ids.values()}


# --- Branches, departments, schedules -------------------------------------------------------


def test_only_admin_creates_branches(client, world):
    body = {"name": "North", "code": "N"}
    assert client.post("/api/v1/branches", headers=world.h("hr"), json=body).status_code == 403
    assert client.post("/api/v1/branches", headers=world.h("admin"), json=body).status_code == 201


def test_hr_manages_departments(client, world):
    r = client.post("/api/v1/departments", headers=world.h("hr"), json={"name": "Finance", "code": "fin"})
    assert r.status_code == 201 and r.json()["code"] == "FIN"
    r = client.put(f"/api/v1/departments/{r.json()['id']}", headers=world.h("hr"), json={"is_active": False})
    assert r.json()["is_active"] is False
    assert client.get("/api/v1/departments", headers=world.h("ann")).status_code == 403


def test_work_schedule_days_are_validated_and_replaced(client, world, test_session_factory):
    day = {"weekday": 0, "start_time": "09:00", "end_time": "18:00"}
    r = client.post("/api/v1/work-schedules", headers=world.h("hr"),
                    json={"name": "Dup", "days": [day, day]})
    assert r.status_code == 422
    r = client.post("/api/v1/work-schedules", headers=world.h("hr"),
                    json={"name": "Bad", "days": [{**day, "end_time": "08:00"}]})
    assert r.status_code == 422

    r = client.post("/api/v1/work-schedules", headers=world.h("hr"), json={
        "name": "Saturday half day", "grace_minutes": 10,
        "days": [day, {"weekday": 5, "start_time": "09:00", "end_time": "13:00"}]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = client.put(f"/api/v1/work-schedules/{sid}", headers=world.h("hr"),
                   json={"days": [{"weekday": 2, "start_time": "08:00", "end_time": "17:00"}]})
    assert [d["weekday"] for d in r.json()["days"]] == [2]
    (entry,) = _audits(test_session_factory, sid, "SCHEDULE_UPDATED")
    assert entry.new_value == {"days": ["2:08:00-17:00"]}


# --- Employees: create, roles, passwords ----------------------------------------------------


def _new_employee(world, **overrides):
    s = uuid.uuid4().hex[:6]
    return {
        "full_name": "New Person", "employee_code": f"emp-{s}", "email": f"New.{s}@Example.com",
        "department_id": str(world.dept_id), "manager_id": str(world.manager_ids["mgr_a"]),
        "location_ids": [str(world.lagos_id), str(world.abuja_id)], **overrides,
    }


def test_hr_creates_employee_who_must_change_temporary_password(client, world, test_session_factory):
    body = _new_employee(world, primary_location_id=str(world.abuja_id))
    r = client.post("/api/v1/employees", headers=world.h("hr"), json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    emp, temp = created["employee"], created["temporary_password"]
    assert emp["email"] == body["email"].lower()
    assert emp["employee_code"] == body["employee_code"].upper()
    assert emp["manager"]["name"] == "Mgr_A"
    assert [l["name"] for l in emp["locations"]] == ["Abuja", "Lagos"]  # primary first
    assert len(_audits(test_session_factory, emp["id"], "EMPLOYEE_CREATED")) == 1

    login = client.post("/api/v1/auth/login", json={"identifier": emp["employee_code"], "password": temp})
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_duplicate_email_or_employee_id_is_refused(client, world):
    body = _new_employee(world, email=world.users["ann"])
    assert client.post("/api/v1/employees", headers=world.h("hr"), json=body).status_code == 409
    body = _new_employee(world, employee_code=f"ANN-{world.users['ann'].split('-')[1][:6]}")
    assert client.post("/api/v1/employees", headers=world.h("hr"), json=body).status_code == 409


def test_primary_location_must_be_in_the_list(client, world):
    body = _new_employee(world, location_ids=[str(world.lagos_id)], primary_location_id=str(world.abuja_id))
    assert client.post("/api/v1/employees", headers=world.h("hr"), json=body).status_code == 422


def test_hr_cannot_create_hr_or_admin_accounts_but_admin_can(client, world):
    for role in ("HR", "ADMIN"):
        r = client.post("/api/v1/employees", headers=world.h("hr"), json=_new_employee(world, role=role))
        assert r.status_code == 403
    r = client.post("/api/v1/employees", headers=world.h("admin"), json=_new_employee(world, role="HR"))
    assert r.status_code == 201


def test_nobody_can_change_their_own_role(client, world):
    r = client.put(f"/api/v1/employees/{world.ids['hr']}", headers=world.h("hr"), json={"role": "ADMIN"})
    assert r.status_code == 403


def test_hr_resets_password(client, world):
    r = client.post(f"/api/v1/employees/{world.ids['ann']}/reset-password", headers=world.h("hr"))
    assert r.status_code == 200
    temp = r.json()["temporary_password"]
    # Old login token and old password stop working; the temporary one works.
    assert client.get("/api/v1/auth/me", headers=world.h("ann")).status_code == 401
    old = client.post("/api/v1/auth/login", json={"identifier": world.users["ann"], "password": PASSWORD})
    assert old.status_code == 401
    new = client.post("/api/v1/auth/login", json={"identifier": world.users["ann"], "password": temp})
    assert new.json()["user"]["must_change_password"] is True


def test_hr_cannot_reset_other_hr_or_admin_passwords(client, world):
    r = client.post("/api/v1/employees", headers=world.h("admin"), json=_new_employee(world, role="HR"))
    other_hr = r.json()["employee"]["id"]
    assert client.post(f"/api/v1/employees/{other_hr}/reset-password", headers=world.h("hr")).status_code == 403
    assert client.post(f"/api/v1/employees/{other_hr}/reset-password", headers=world.h("admin")).status_code == 200


def test_suspending_an_employee_ends_their_access(client, world):
    r = client.put(f"/api/v1/employees/{world.ids['ben']}", headers=world.h("hr"),
                   json={"employment_status": "SUSPENDED"})
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=world.h("ben")).status_code == 401


# --- Locations of an employee ---------------------------------------------------------------


def test_changing_employee_locations_is_audited(client, world, test_session_factory):
    r = client.put(f"/api/v1/employees/{world.ids['ann']}/locations", headers=world.h("hr"),
                   json={"location_ids": [str(world.abuja_id)]})
    assert r.status_code == 200
    assert [l["name"] for l in r.json()["locations"]] == ["Abuja"]
    (entry,) = _audits(test_session_factory, world.ids["ann"], "EMPLOYEE_LOCATIONS_CHANGED")
    assert entry.old_value == {"locations": [f"{world.lagos_id} (primary)"]}
    assert entry.new_value == {"locations": [f"{world.abuja_id} (primary)"]}


def test_inactive_location_cannot_be_assigned(client, world):
    client.put(f"/api/v1/locations/{world.abuja_id}", headers=world.h("hr"), json={"is_active": False})
    r = client.put(f"/api/v1/employees/{world.ids['ann']}/locations", headers=world.h("hr"),
                   json={"location_ids": [str(world.abuja_id)]})
    assert r.status_code == 422


# --- Manager scoping ------------------------------------------------------------------------


def test_manager_sees_only_their_team(client, world):
    r = client.get("/api/v1/employees", headers=world.h("mgr_a"))
    assert r.status_code == 200
    assert sorted(e["full_name"] for e in r.json()["items"]) == ["Ann", "Ben"]
    assert client.get(f"/api/v1/employees/{world.ids['ann']}", headers=world.h("mgr_a")).status_code == 200
    # Other manager's employee: same 404 as a non-existent one.
    assert client.get(f"/api/v1/employees/{world.ids['cal']}", headers=world.h("mgr_a")).status_code == 404


def test_manager_cannot_modify_employees(client, world):
    r = client.put(f"/api/v1/employees/{world.ids['ann']}", headers=world.h("mgr_a"), json={"full_name": "X"})
    assert r.status_code == 403
    r = client.post(f"/api/v1/employees/{world.ids['ann']}/reset-password", headers=world.h("mgr_a"))
    assert r.status_code == 403


def test_employee_cannot_list_employees(client, world):
    assert client.get("/api/v1/employees", headers=world.h("ann")).status_code == 403


def test_hr_sees_everyone_and_can_filter(client, world):
    everyone = client.get("/api/v1/employees", headers=world.h("hr")).json()
    assert everyone["total"] == 6  # hr, 2 managers, 3 employees (admin has no employee record)
    abuja = client.get(f"/api/v1/employees?location_id={world.abuja_id}", headers=world.h("hr")).json()
    assert sorted(e["full_name"] for e in abuja["items"]) == ["Cal", "Mgr_B"]
    search = client.get("/api/v1/employees?q=ann", headers=world.h("hr")).json()
    assert [e["full_name"] for e in search["items"]] == ["Ann"]
    page = client.get("/api/v1/employees?page=2&page_size=4", headers=world.h("hr")).json()
    assert len(page["items"]) == 2 and page["total"] == 6


def test_promote_to_manager_and_demotion_requires_empty_team(client, world):
    r = client.put(f"/api/v1/employees/{world.ids['ben']}", headers=world.h("hr"), json={"role": "MANAGER"})
    assert r.status_code == 200
    managers = {m["name"]: m for m in client.get("/api/v1/managers", headers=world.h("hr")).json()}
    assert "Ben" in managers

    client.put(f"/api/v1/employees/{world.ids['ann']}", headers=world.h("hr"),
               json={"manager_id": managers["Ben"]["id"]})
    r = client.put(f"/api/v1/employees/{world.ids['ben']}", headers=world.h("hr"), json={"role": "EMPLOYEE"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "MANAGER_HAS_TEAM"


def test_employee_cannot_be_own_manager(client, world):
    r = client.put(f"/api/v1/employees/{world.ids['mgr_a']}", headers=world.h("hr"),
                   json={"manager_id": str(world.manager_ids["mgr_a"])})
    assert r.status_code == 422


# --- Employee's own profile -----------------------------------------------------------------


def test_employee_profile_and_phone_update(client, world, test_session_factory):
    me = client.get("/api/v1/employees/me", headers=world.h("ann")).json()
    assert me["full_name"] == "Ann" and me["manager"] == "Mgr_A" and me["department"] == "Ops"
    assert [l["name"] for l in me["locations"]] == ["Lagos"]
    assert "latitude" not in me["locations"][0]  # no coordinates needed by the employee

    r = client.put("/api/v1/employees/me", headers=world.h("ann"), json={"phone": "+234 801 234 5678"})
    assert r.status_code == 200 and r.json()["phone"] == "+234 801 234 5678"
    assert len(_audits(test_session_factory, world.ids["ann"], "OWN_PROFILE_UPDATED")) == 1


def test_employee_cannot_edit_other_profile_fields(client, world):
    r = client.put("/api/v1/employees/me", headers=world.h("ann"), json={"full_name": "Boss"})
    assert r.status_code == 422
