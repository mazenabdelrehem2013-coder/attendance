"""Phase 20: every API endpoint, called automatically by people who must NOT get in.

New endpoints are picked up by themselves, so a forgotten permission check fails this test.
  - nobody logged in             -> 401 everywhere except the few public endpoints
  - an EMPLOYEE                  -> only their own things (profile, attendance, phone, alerts)
  - a MANAGER                    -> additionally team views and reports, never HR/admin functions
"""

import re
import uuid

import pytest

from app.main import create_app

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/ready"),  # only "database ok" + schema version
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/qr/current"),  # office screen: refuses everyone without its own secret display key
}

# What an employee may use (everything else must be refused). The scoping of the shared lists
# (leave: own only, locations: assigned only) is tested below.
EMPLOYEE_ALLOWED = re.compile(
    r"^(GET|POST|PUT) /api/v1/(auth/.*|employees/me|attendance/.*|devices/register|devices/me|"
    r"notifications|notifications/.*)$|^GET /api/v1/(holidays|leave|locations)$"
)
# What a manager may additionally use - always limited to their own team (tested below).
MANAGER_ALLOWED = re.compile(
    r"^(GET|POST) /api/v1/(manager/.*|reports/.*)$"
    r"|^GET /api/v1/(managers|departments|branches|work-schedules|employees|hr/attendance)$"
)


def routes():
    """Every endpoint, from the API's own OpenAPI description."""
    paths = create_app().openapi()["paths"]
    return sorted((m.upper(), p) for p, ops in paths.items() for m in ops if p.startswith("/api/v1"))


ALL = routes()


def call(client, method, path, headers=None):
    url = re.sub(r"\{[^}]+\}", lambda m: "RETENTION" if "category" in m.group(0) else str(uuid.uuid4()), path)
    url = url.replace("RETENTION", "RAW_LOCATION")
    body = {} if method in ("POST", "PUT", "PATCH") else None
    return client.request(method, url, headers=headers or {}, json=body)


def test_route_list_is_complete():
    assert len(ALL) >= 95  # guards against the discovery silently finding nothing


@pytest.mark.parametrize("method,path", [r for r in ALL if r not in PUBLIC])
def test_nobody_logged_in_is_refused(client, method, path):
    r = call(client, method, path)
    assert r.status_code == 401, f"{method} {path} answered {r.status_code} without login"


@pytest.mark.parametrize("method,path", ALL)
def test_employee_cannot_use_staff_functions(client, world, method, path):
    if (method, path) in PUBLIC or EMPLOYEE_ALLOWED.match(f"{method} {path}"):
        pytest.skip("allowed for employees")
    r = call(client, method, path, world.h("ann"))
    assert r.status_code in (403, 404), f"{method} {path}: employee got {r.status_code}"


@pytest.mark.parametrize("method,path", ALL)
def test_manager_cannot_use_hr_functions(client, world, method, path):
    key = f"{method} {path}"
    if (method, path) in PUBLIC or EMPLOYEE_ALLOWED.match(key) or MANAGER_ALLOWED.match(key):
        pytest.skip("allowed for managers")
    r = call(client, method, path, world.h("mgr_a"))
    assert r.status_code in (403, 404), f"{key}: manager got {r.status_code}"


# --- The shared lists only show what each person may see ------------------------------------


def test_employee_sees_only_own_leave_and_own_offices(client, world):
    hr = world.h("hr")
    for who in ("ann", "ben"):
        r = client.post("/api/v1/leave", headers=hr, json={"employee_id": str(world.ids[who]), "leave_type": "ANNUAL",
                                                            "start_date": "2026-11-02", "end_date": "2026-11-03"})
        assert r.status_code == 201, r.text
    leave = client.get("/api/v1/leave", headers=world.h("ann")).json()
    assert {item["employee_id"] for item in leave} == {str(world.ids["ann"])}
    other = client.get("/api/v1/leave", headers=world.h("ann"), params={"employee_id": str(world.ids["ben"])}).json()
    assert other == []
    assert [loc["name"] for loc in client.get("/api/v1/locations", headers=world.h("ann")).json()] == ["Lagos"]


def test_manager_lists_only_their_team(client, world):
    staff = client.get("/api/v1/employees", headers=world.h("mgr_b")).json()["items"]
    assert [e["full_name"] for e in staff] == ["Cal"]
    day = client.get("/api/v1/hr/attendance", headers=world.h("mgr_b")).json()
    assert [r["full_name"] for r in day["rows"]] == ["Cal"]
    leave = client.get("/api/v1/leave", headers=world.h("mgr_b"), params={"employee_id": str(world.ids["ann"])}).json()
    assert leave == []
