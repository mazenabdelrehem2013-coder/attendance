"""A complete small test company in its own organization, so tests never collide."""

import uuid
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models import (
    Branch,
    Department,
    Employee,
    EmployeeLocation,
    Location,
    Manager,
    Organization,
    User,
    WorkSchedule,
    WorkScheduleDay,
)
from app.models.enums import Role
from tests.api.conftest import PASSWORD, auth_header


@dataclass
class World:
    """A complete small company in its own organization (so tests never collide)."""

    org_id: uuid.UUID
    branch_id: uuid.UUID
    dept_id: uuid.UUID
    schedule_id: uuid.UUID
    lagos_id: uuid.UUID
    abuja_id: uuid.UUID
    ids: dict = field(default_factory=dict)  # name -> employee id
    users: dict = field(default_factory=dict)  # name -> email
    manager_ids: dict = field(default_factory=dict)  # name -> managers.id
    tokens: dict = field(default_factory=dict)

    def h(self, who: str) -> dict:
        return auth_header(self.tokens[who])


_PASSWORD_HASH = hash_password(PASSWORD)  # hashing is deliberately slow; do it once


def build_world(session_factory, client) -> World:
    s = uuid.uuid4().hex[:6]
    with session_factory.begin() as db:
        org = Organization(name=f"World {s}")
        db.add(org)
        db.flush()
        branch = Branch(organization_id=org.id, name="Main", code="MAIN")
        dept = Department(organization_id=org.id, name="Ops", code="OPS")
        sched = WorkSchedule(
            organization_id=org.id, name="Std",
            days=[WorkScheduleDay(weekday=d, start_time=time(9), end_time=time(18)) for d in range(6)],
        )
        db.add_all([branch, dept, sched])
        db.flush()
        lagos = Location(organization_id=org.id, branch_id=branch.id, name="Lagos", code="LOS",
                         latitude=Decimal("6.4281"), longitude=Decimal("3.4219"), work_schedule_id=sched.id)
        abuja = Location(organization_id=org.id, branch_id=branch.id, name="Abuja", code="ABV",
                         latitude=Decimal("9.0563"), longitude=Decimal("7.4985"), work_schedule_id=sched.id)
        db.add_all([lagos, abuja])
        db.flush()
        w = World(org.id, branch.id, dept.id, sched.id, lagos.id, abuja.id)

        def person(name, role, loc, with_employee=True):
            email = f"{name}-{s}@example.com"
            user = User(organization_id=org.id, email=email, password_hash=_PASSWORD_HASH,
                        role=role, must_change_password=False)
            db.add(user)
            db.flush()
            w.users[name] = email
            if not with_employee:
                return None
            emp = Employee(organization_id=org.id, user_id=user.id, employee_code=f"{name.upper()}-{s}",
                           full_name=name.title(), department_id=dept.id, hire_date=date(2025, 1, 1))
            db.add(emp)
            db.flush()
            # Valid from the hire date: tests move the clock to fixed dates (Oct 2026), which can be
            # before the database's real "today" (the default start of an assignment).
            db.add(EmployeeLocation(employee_id=emp.id, location_id=loc, is_primary=True,
                                    valid_from=date(2025, 1, 1)))
            w.ids[name] = emp.id
            if role == Role.MANAGER:
                m = Manager(user_id=user.id, employee_id=emp.id)
                db.add(m)
                db.flush()
                w.manager_ids[name] = m.id
            return emp

        person("admin", Role.ADMIN, None, with_employee=False)
        person("hr", Role.HR, lagos.id)
        person("mgr_a", Role.MANAGER, lagos.id)
        person("mgr_b", Role.MANAGER, abuja.id)
        for name, mgr, loc in [("ann", "mgr_a", lagos.id), ("ben", "mgr_a", lagos.id), ("cal", "mgr_b", abuja.id)]:
            person(name, Role.EMPLOYEE, loc).manager_id = w.manager_ids[mgr]

    for who, email in w.users.items():
        r = client.post("/api/v1/auth/login", json={"identifier": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        w.tokens[who] = r.json()["access_token"]
    return w


@pytest.fixture
def world(test_session_factory, client) -> World:
    return build_world(test_session_factory, client)
