"""Branches, departments, work schedules and locations.

Read:  managers, HR and admins (dropdowns, filters). Employees see only their own locations.
Write: HR and admins (branches: admins only). Nothing is ever deleted - set is_active=false.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, get_current_user, require_roles
from app.db.session import get_db
from app.models import Employee, EmployeeLocation, Location, User
from app.models.enums import Role
from app.schemas.org import (
    BranchCreate,
    BranchOut,
    BranchUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    LocationCreate,
    LocationOut,
    LocationUpdate,
    ScheduleCreate,
    ScheduleOut,
    ScheduleUpdate,
)
from app.services import org_service
from app.services.audit import Actor

router = APIRouter(tags=["organization"])

staff = require_roles(Role.MANAGER, Role.HR)
hr_actor = actor_with_roles(Role.HR)
admin_actor = actor_with_roles(Role.ADMIN)


# --- Branches -------------------------------------------------------------------------------


@router.get("/branches", response_model=list[BranchOut])
def list_branches(user: User = Depends(staff), db: Session = Depends(get_db)):
    return org_service.list_branches(db, user.organization_id)


@router.post("/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(body: BranchCreate, actor: Actor = Depends(admin_actor), db: Session = Depends(get_db)):
    return org_service.create_branch(db, actor, body)


@router.put("/branches/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: uuid.UUID, body: BranchUpdate,
    actor: Actor = Depends(admin_actor), db: Session = Depends(get_db),
):
    return org_service.update_branch(db, actor, branch_id, body)


# --- Departments ----------------------------------------------------------------------------


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(user: User = Depends(staff), db: Session = Depends(get_db)):
    return org_service.list_departments(db, user.organization_id)


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(
    body: DepartmentCreate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)
):
    return org_service.create_department(db, actor, body)


@router.put("/departments/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: uuid.UUID, body: DepartmentUpdate,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return org_service.update_department(db, actor, department_id, body)


# --- Work schedules -------------------------------------------------------------------------


@router.get("/work-schedules", response_model=list[ScheduleOut])
def list_schedules(user: User = Depends(staff), db: Session = Depends(get_db)):
    return org_service.list_schedules(db, user.organization_id)


@router.post("/work-schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduleCreate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)
):
    return org_service.create_schedule(db, actor, body)


@router.put("/work-schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: uuid.UUID, body: ScheduleUpdate,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return org_service.update_schedule(db, actor, schedule_id, body)


# --- Locations ------------------------------------------------------------------------------


@router.get("/locations", response_model=list[LocationOut])
def list_locations(
    include_inactive: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(Location).where(Location.organization_id == user.organization_id)
    if user.role == Role.EMPLOYEE:
        # Employees only see the locations they are assigned to.
        query = query.join(EmployeeLocation, EmployeeLocation.location_id == Location.id).join(
            Employee, Employee.id == EmployeeLocation.employee_id
        ).where(Employee.user_id == user.id)
    if not include_inactive:
        query = query.where(Location.is_active)
    return list(db.scalars(query.order_by(Location.name)))


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    body: LocationCreate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)
):
    return org_service.create_location(db, actor, body)


@router.get("/locations/{location_id}", response_model=LocationOut)
def get_location(location_id: uuid.UUID, user: User = Depends(staff), db: Session = Depends(get_db)):
    return org_service.get_in_org(db, Location, location_id, user.organization_id, "Location")


@router.put("/locations/{location_id}", response_model=LocationOut)
def update_location(
    location_id: uuid.UUID, body: LocationUpdate,
    actor: Actor = Depends(hr_actor), db: Session = Depends(get_db),
):
    return org_service.update_location(db, actor, location_id, body)
