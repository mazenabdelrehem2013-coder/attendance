"""Employees and managers.

Managers see only their own team (read-only). HR and admins manage everyone.
Employees use /employees/me for their own profile.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, get_current_user, request_info, require_roles
from app.db.session import get_db
from app.models import User
from app.models.enums import EmploymentStatus, Role
from app.schemas.common import Page, PageParams
from app.schemas.employees import (
    EmployeeCreate,
    EmployeeCreated,
    EmployeeOut,
    EmployeeUpdate,
    LocationAssignment,
    ManagerOut,
    MyProfile,
    MyProfileUpdate,
    PasswordReset,
)
from app.services import employee_service
from app.services.audit import Actor, RequestInfo
from app.services.employee_service import EmployeeFilters

router = APIRouter(tags=["employees"])

staff = require_roles(Role.MANAGER, Role.HR)
hr_actor = actor_with_roles(Role.HR)


# Declared before /employees/{employee_id} so "me" isn't read as an id.
@router.get("/employees/me", response_model=MyProfile, summary="My profile")
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return employee_service.my_profile(db, user)


@router.put("/employees/me", response_model=MyProfile, summary="Update my phone number")
def update_me(
    body: MyProfileUpdate,
    user: User = Depends(get_current_user),
    info: RequestInfo = Depends(request_info),
    db: Session = Depends(get_db),
):
    return employee_service.update_my_profile(db, Actor(user, info), body)


@router.get("/employees", response_model=Page[EmployeeOut])
def list_employees(
    q: str | None = Query(None, max_length=100, description="Search name, employee ID or email"),
    department_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    manager_id: uuid.UUID | None = None,
    role: Role | None = None,
    employment_status: EmploymentStatus | None = None,
    page: PageParams = Depends(),
    user: User = Depends(staff),
    db: Session = Depends(get_db),
):
    filters = EmployeeFilters(q, department_id, location_id, manager_id, role, employment_status)
    return employee_service.list_employees(db, user, filters, page)


@router.post("/employees", response_model=EmployeeCreated, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: EmployeeCreate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)
):
    employee, temp_password = employee_service.create_employee(db, actor, body)
    return EmployeeCreated(employee=employee, temporary_password=temp_password)


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: uuid.UUID, user: User = Depends(staff), db: Session = Depends(get_db)):
    return employee_service.get_employee(db, user, employee_id)


@router.put("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: uuid.UUID, body: EmployeeUpdate,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return employee_service.update_employee(db, actor, employee_id, body)


@router.put("/employees/{employee_id}/locations", response_model=EmployeeOut,
            summary="Set the locations where this employee may check in")
def set_locations(
    employee_id: uuid.UUID, body: LocationAssignment,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return employee_service.set_employee_locations(db, actor, employee_id, body)


@router.post("/employees/{employee_id}/reset-password", response_model=PasswordReset,
             summary="Give the employee a new temporary password")
def reset_password(
    employee_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)
):
    return PasswordReset(temporary_password=employee_service.reset_password(db, actor, employee_id))


@router.get("/managers", response_model=list[ManagerOut], summary="Active managers (for dropdowns)")
def list_managers(user: User = Depends(require_roles(Role.HR)), db: Session = Depends(get_db)):
    return employee_service.list_managers(db, user.organization_id)
