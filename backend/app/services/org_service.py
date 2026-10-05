"""Branches, departments, work schedules and locations. Every change is audit-logged."""

import uuid
from contextlib import contextmanager
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.models import Branch, Department, Location, WorkSchedule, WorkScheduleDay
from app.schemas.org import (
    BranchCreate,
    BranchUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    LocationCreate,
    LocationUpdate,
    ScheduleCreate,
    ScheduleUpdate,
)
from app.services.audit import Actor, audit, changed_fields, snapshot

M = TypeVar("M")

BRANCH_FIELDS = ["name", "code", "is_active"]
DEPARTMENT_FIELDS = ["name", "code", "branch_id", "is_active"]
SCHEDULE_FIELDS = ["name", "grace_minutes", "early_departure_minutes", "is_active"]
LOCATION_FIELDS = [
    "branch_id", "name", "code", "address", "latitude", "longitude", "radius_m", "timezone",
    "work_schedule_id", "is_active",
]


def get_in_org(db: Session, model: type[M], obj_id: uuid.UUID, org_id: uuid.UUID, label: str) -> M:
    obj = db.get(model, obj_id)
    if obj is None or obj.organization_id != org_id:
        raise AppError(404, "NOT_FOUND", f"{label} not found.")
    return obj


@contextmanager
def _unique(db: Session, duplicate_message: str):
    """Run a change and commit it; a unique-constraint clash (at flush or commit) becomes 409."""
    try:
        yield
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "DUPLICATE", duplicate_message) from None


# Fields that may be cleared by sending null; any other field sent as null is an error.
NULLABLE = {"branch_id", "address", "work_schedule_id"}


def _apply(obj, data: BaseModel, nullable: set[str] = NULLABLE) -> None:
    for field in data.model_fields_set:
        value = getattr(data, field)
        if value is None and field not in nullable:
            raise AppError(422, "VALIDATION_ERROR", f"'{field}' cannot be empty.")
        setattr(obj, field, value)


def _create(db: Session, actor: Actor, obj, fields: list[str], action: str, label: str):
    db.add(obj)
    db.flush()
    audit(db, actor, action, label, obj.id, new_value=snapshot(obj, fields))
    return obj


def _update(db: Session, actor: Actor, obj, data: BaseModel, fields, action: str, label: str):
    before = snapshot(obj, fields)
    _apply(obj, data)
    db.flush()
    old, new = changed_fields(before, snapshot(obj, fields))
    if new:
        audit(db, actor, action, label, obj.id, old_value=old, new_value=new)
    return obj


# --- Branches -------------------------------------------------------------------------------


def list_branches(db: Session, org_id: uuid.UUID) -> list[Branch]:
    return list(db.scalars(select(Branch).where(Branch.organization_id == org_id).order_by(Branch.name)))


def create_branch(db: Session, actor: Actor, data: BranchCreate) -> Branch:
    org = actor.user.organization_id
    with _unique(db, "A branch with this code already exists."):
        branch = _create(db, actor, Branch(organization_id=org, **data.model_dump()), BRANCH_FIELDS,
                         "BRANCH_CREATED", "branch")
    return branch


def update_branch(db: Session, actor: Actor, branch_id: uuid.UUID, data: BranchUpdate) -> Branch:
    branch = get_in_org(db, Branch, branch_id, actor.user.organization_id, "Branch")
    with _unique(db, "A branch with this code already exists."):
        _update(db, actor, branch, data, BRANCH_FIELDS, "BRANCH_UPDATED", "branch")
    return branch


# --- Departments ----------------------------------------------------------------------------


def list_departments(db: Session, org_id: uuid.UUID) -> list[Department]:
    return list(
        db.scalars(
            select(Department).where(Department.organization_id == org_id).order_by(Department.name)
        )
    )


def _check_branch(db: Session, actor: Actor, branch_id: uuid.UUID | None) -> None:
    if branch_id is not None:
        get_in_org(db, Branch, branch_id, actor.user.organization_id, "Branch")


def create_department(db: Session, actor: Actor, data: DepartmentCreate) -> Department:
    _check_branch(db, actor, data.branch_id)
    dept = Department(organization_id=actor.user.organization_id, **data.model_dump())
    with _unique(db, "A department with this code already exists."):
        _create(db, actor, dept, DEPARTMENT_FIELDS, "DEPARTMENT_CREATED", "department")
    return dept


def update_department(
    db: Session, actor: Actor, dept_id: uuid.UUID, data: DepartmentUpdate
) -> Department:
    dept = get_in_org(db, Department, dept_id, actor.user.organization_id, "Department")
    _check_branch(db, actor, data.branch_id)
    with _unique(db, "A department with this code already exists."):
        _update(db, actor, dept, data, DEPARTMENT_FIELDS, "DEPARTMENT_UPDATED", "department")
    return dept


# --- Work schedules -------------------------------------------------------------------------


def _schedule_snapshot(schedule: WorkSchedule) -> dict:
    data = snapshot(schedule, SCHEDULE_FIELDS)
    data["days"] = [
        f"{d.weekday}:{d.start_time.isoformat('minutes')}-{d.end_time.isoformat('minutes')}"
        for d in sorted(schedule.days, key=lambda d: d.weekday)
    ]
    return data


def list_schedules(db: Session, org_id: uuid.UUID) -> list[WorkSchedule]:
    return list(
        db.scalars(
            select(WorkSchedule)
            .where(WorkSchedule.organization_id == org_id)
            .options(selectinload(WorkSchedule.days))
            .order_by(WorkSchedule.name)
        )
    )


def create_schedule(db: Session, actor: Actor, data: ScheduleCreate) -> WorkSchedule:
    schedule = WorkSchedule(
        organization_id=actor.user.organization_id,
        name=data.name,
        grace_minutes=data.grace_minutes,
        early_departure_minutes=data.early_departure_minutes,
        days=[WorkScheduleDay(**d.model_dump()) for d in data.days],
    )
    with _unique(db, "A schedule with this name already exists."):
        db.add(schedule)
        db.flush()
        audit(db, actor, "SCHEDULE_CREATED", "work_schedule", schedule.id,
              new_value=_schedule_snapshot(schedule))
    return schedule


def update_schedule(
    db: Session, actor: Actor, schedule_id: uuid.UUID, data: ScheduleUpdate
) -> WorkSchedule:
    schedule = get_in_org(db, WorkSchedule, schedule_id, actor.user.organization_id, "Schedule")
    before = _schedule_snapshot(schedule)
    for field in data.model_fields_set - {"days"}:
        if getattr(data, field) is None:
            raise AppError(422, "VALIDATION_ERROR", f"'{field}' cannot be empty.")
    with _unique(db, "A schedule with this name already exists."):
        for field in data.model_fields_set - {"days"}:
            setattr(schedule, field, getattr(data, field))
        if "days" in data.model_fields_set and data.days is not None:
            schedule.days.clear()
            db.flush()  # remove old days first (weekday must stay unique)
            schedule.days.extend(WorkScheduleDay(**d.model_dump()) for d in data.days)
        db.flush()
        old, new = changed_fields(before, _schedule_snapshot(schedule))
        if new:
            audit(db, actor, "SCHEDULE_UPDATED", "work_schedule", schedule.id, old, new)
    return schedule


# --- Locations ------------------------------------------------------------------------------


def _check_location_refs(db: Session, actor: Actor, data: LocationCreate | LocationUpdate) -> None:
    org = actor.user.organization_id
    if data.branch_id is not None:
        get_in_org(db, Branch, data.branch_id, org, "Branch")
    if data.work_schedule_id is not None:
        get_in_org(db, WorkSchedule, data.work_schedule_id, org, "Schedule")


def create_location(db: Session, actor: Actor, data: LocationCreate) -> Location:
    _check_location_refs(db, actor, data)
    loc = Location(organization_id=actor.user.organization_id, **data.model_dump())
    with _unique(db, "A location with this code already exists."):
        _create(db, actor, loc, LOCATION_FIELDS, "LOCATION_CREATED", "location")
    return loc


def update_location(db: Session, actor: Actor, loc_id: uuid.UUID, data: LocationUpdate) -> Location:
    loc = get_in_org(db, Location, loc_id, actor.user.organization_id, "Location")
    _check_location_refs(db, actor, data)
    with _unique(db, "A location with this code already exists."):
        _update(db, actor, loc, data, LOCATION_FIELDS, "LOCATION_UPDATED", "location")
    return loc
