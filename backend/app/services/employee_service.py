"""Employees, their accounts, managers and authorized locations."""

import secrets
import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.errors import AppError
from app.core.security import hash_password
from app.models import (
    Department,
    Employee,
    EmployeeLocation,
    Location,
    Manager,
    User,
    WorkSchedule,
)
from app.models.enums import EmploymentStatus, Role
from app.schemas.common import Page, PageParams
from app.schemas.employees import (
    AssignedLocation,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    LocationAssignment,
    ManagerOut,
    MyProfile,
    MyProfileUpdate,
    Ref,
)
from app.schemas.org import LocationBrief
from app.services.audit import Actor, audit, changed_fields
from app.services.auth_service import revoke_all_for_user
from app.services.org_service import get_in_org
from app.services.scope import employee_scope, get_visible_employee

# Roles HR may hand out. Only ADMIN may create or change HR/ADMIN accounts.
HR_ASSIGNABLE_ROLES = {Role.EMPLOYEE, Role.MANAGER}
PRIVILEGED_ROLES = {Role.HR, Role.ADMIN}

_LOADERS = (
    selectinload(Employee.user),
    selectinload(Employee.department),
    selectinload(Employee.manager).selectinload(Manager.employee),
    selectinload(Employee.manager).selectinload(Manager.user),
    selectinload(Employee.locations).selectinload(EmployeeLocation.location),
)


@dataclass
class EmployeeFilters:
    q: str | None = None
    department_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    role: Role | None = None
    employment_status: EmploymentStatus | None = None


# --- Output ---------------------------------------------------------------------------------


def _manager_name(manager: Manager) -> str:
    return manager.employee.full_name if manager.employee else manager.user.email


def to_out(emp: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=emp.id,
        user_id=emp.user_id,
        employee_code=emp.employee_code,
        full_name=emp.full_name,
        email=emp.user.email,
        phone=emp.phone,
        role=emp.user.role,
        is_active=emp.user.is_active,
        employment_status=emp.employment_status,
        hire_date=emp.hire_date,
        department=Ref(id=emp.department.id, name=emp.department.name) if emp.department else None,
        manager=Ref(id=emp.manager.id, name=_manager_name(emp.manager)) if emp.manager else None,
        work_schedule_id=emp.work_schedule_id,
        locations=sorted(
            (
                AssignedLocation(location_id=el.location_id, name=el.location.name, is_primary=el.is_primary)
                for el in emp.locations
            ),
            key=lambda a: (not a.is_primary, a.name),
        ),
    )


def _audit_view(emp: Employee) -> dict:
    """Flat, comparable picture of an employee for audit old/new values."""
    return {
        "full_name": emp.full_name,
        "email": emp.user.email,
        "phone": emp.phone,
        "role": emp.user.role.value,
        "is_active": emp.user.is_active,
        "employment_status": emp.employment_status.value,
        "department_id": str(emp.department_id) if emp.department_id else None,
        "manager_id": str(emp.manager_id) if emp.manager_id else None,
        "work_schedule_id": str(emp.work_schedule_id) if emp.work_schedule_id else None,
        "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
        "locations": sorted(
            f"{el.location_id}{' (primary)' if el.is_primary else ''}" for el in emp.locations
        ),
    }


def _load(db: Session, employee_id: uuid.UUID) -> Employee:
    db.expire_all()
    return db.scalar(select(Employee).where(Employee.id == employee_id).options(*_LOADERS))


# --- Read -----------------------------------------------------------------------------------


def list_employees(
    db: Session, user: User, filters: EmployeeFilters, page: PageParams
) -> Page[EmployeeOut]:
    query = select(Employee).join(User, User.id == Employee.user_id).where(employee_scope(db, user))
    if filters.q:
        like = f"%{filters.q.strip()}%"
        query = query.where(
            or_(Employee.full_name.ilike(like), Employee.employee_code.ilike(like), User.email.ilike(like))
        )
    if filters.department_id:
        query = query.where(Employee.department_id == filters.department_id)
    if filters.manager_id:
        query = query.where(Employee.manager_id == filters.manager_id)
    if filters.role:
        query = query.where(User.role == filters.role)
    if filters.employment_status:
        query = query.where(Employee.employment_status == filters.employment_status)
    if filters.location_id:
        query = query.where(
            Employee.id.in_(
                select(EmployeeLocation.employee_id).where(
                    EmployeeLocation.location_id == filters.location_id
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.options(*_LOADERS)
        .order_by(Employee.full_name, Employee.employee_code)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return Page(items=[to_out(e) for e in rows], total=total, page=page.page, page_size=page.page_size)


def get_employee(db: Session, user: User, employee_id: uuid.UUID) -> EmployeeOut:
    get_visible_employee(db, user, employee_id)
    return to_out(_load(db, employee_id))


def list_managers(db: Session, org_id: uuid.UUID) -> list[ManagerOut]:
    team_size = (
        select(func.count())
        .select_from(Employee)
        .where(Employee.manager_id == Manager.id)
        .correlate(Manager)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Manager, team_size)
        .join(User, User.id == Manager.user_id)
        .where(User.organization_id == org_id, Manager.is_active)
        .options(selectinload(Manager.employee), selectinload(Manager.user))
    ).all()
    managers = [
        ManagerOut(
            id=m.id, user_id=m.user_id, employee_id=m.employee_id,
            name=_manager_name(m), email=m.user.email, team_size=size,
        )
        for m, size in rows
    ]
    return sorted(managers, key=lambda m: m.name)


# --- Validation helpers ---------------------------------------------------------------------


def _check_role_change_allowed(actor: Actor, target_current_role: Role | None, new_role: Role) -> None:
    if actor.user.role == Role.ADMIN:
        return
    if new_role not in HR_ASSIGNABLE_ROLES or (target_current_role in PRIVILEGED_ROLES):
        raise AppError(403, "FORBIDDEN", "Only an administrator can give or change HR/Admin access.")


def _check_can_manage(actor: Actor, emp: Employee) -> None:
    """HR may not modify administrators' or other HR staff's accounts (except via ADMIN)."""
    if actor.user.role != Role.ADMIN and emp.user.role in PRIVILEGED_ROLES and emp.user_id != actor.user.id:
        raise AppError(403, "FORBIDDEN", "Only an administrator can change HR or Admin accounts.")


def _active_manager(db: Session, org_id: uuid.UUID, manager_id: uuid.UUID) -> Manager:
    manager = db.get(Manager, manager_id)
    if manager is None or not manager.is_active or manager.user.organization_id != org_id:
        raise AppError(404, "NOT_FOUND", "Manager not found.")
    return manager


def _email_taken(db: Session, email: str, except_user: uuid.UUID | None = None) -> bool:
    query = select(User.id).where(func.lower(User.email) == email.lower())
    if except_user:
        query = query.where(User.id != except_user)
    return db.scalar(query) is not None


def _code_taken(db: Session, org_id: uuid.UUID, code: str) -> bool:
    return (
        db.scalar(
            select(Employee.id).where(
                Employee.organization_id == org_id, func.upper(Employee.employee_code) == code.upper()
            )
        )
        is not None
    )


def _sync_manager_record(db: Session, emp: Employee, old_role: Role | None, new_role: Role) -> None:
    """Keep the managers table in line with the user's role."""
    manager = db.scalar(select(Manager).where(Manager.user_id == emp.user_id))
    if new_role == Role.MANAGER:
        if manager is None:
            db.add(Manager(user_id=emp.user_id, employee_id=emp.id, is_active=True))
        else:
            manager.is_active = True
            manager.employee_id = emp.id
    elif old_role == Role.MANAGER and manager is not None:
        team = db.scalar(select(func.count()).select_from(Employee).where(Employee.manager_id == manager.id))
        if team:
            raise AppError(
                409, "MANAGER_HAS_TEAM",
                f"This manager still has {team} employee(s). Assign them to another manager first.",
            )
        manager.is_active = False


def _set_locations(db: Session, org_id: uuid.UUID, emp: Employee, data: LocationAssignment, actor_id) -> None:
    locations = db.scalars(
        select(Location).where(Location.id.in_(data.location_ids), Location.organization_id == org_id)
    ).all()
    found = {loc.id: loc for loc in locations}
    missing = [str(i) for i in data.location_ids if i not in found]
    if missing:
        raise AppError(404, "NOT_FOUND", "Location not found.")
    if any(not loc.is_active for loc in locations):
        raise AppError(422, "LOCATION_INACTIVE", "Inactive locations can't be assigned.")

    emp.locations.clear()
    db.flush()  # remove old assignments before inserting (one primary per employee)
    now = clock.now()
    for loc_id in data.location_ids:
        emp.locations.append(
            EmployeeLocation(
                location_id=loc_id, is_primary=(loc_id == data.primary_location_id), created_by=actor_id,
                # Valid from today AT THAT OFFICE (the database's own date is UTC and could differ).
                valid_from=now.astimezone(ZoneInfo(found[loc_id].timezone)).date(),
            )
        )


def generate_temporary_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # no 0/O, 1/l/I
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


# --- Write ----------------------------------------------------------------------------------


def create_employee(db: Session, actor: Actor, data: EmployeeCreate) -> tuple[EmployeeOut, str]:
    org = actor.user.organization_id
    _check_role_change_allowed(actor, None, data.role)
    if _email_taken(db, data.email):
        raise AppError(409, "DUPLICATE", "A user with this email already exists.")
    if _code_taken(db, org, data.employee_code):
        raise AppError(409, "DUPLICATE", "An employee with this employee ID already exists.")
    if data.department_id:
        get_in_org(db, Department, data.department_id, org, "Department")
    if data.work_schedule_id:
        get_in_org(db, WorkSchedule, data.work_schedule_id, org, "Schedule")
    if data.manager_id:
        _active_manager(db, org, data.manager_id)

    temp_password = generate_temporary_password()
    user = User(
        organization_id=org,
        email=data.email,
        password_hash=hash_password(temp_password),
        role=data.role,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    emp = Employee(
        organization_id=org,
        user_id=user.id,
        employee_code=data.employee_code,
        full_name=data.full_name,
        phone=data.phone,
        department_id=data.department_id,
        manager_id=data.manager_id,
        work_schedule_id=data.work_schedule_id,
        hire_date=data.hire_date,
    )
    db.add(emp)
    db.flush()
    _set_locations(db, org, emp, data, actor.user.id)
    _sync_manager_record(db, emp, None, data.role)
    db.flush()

    emp = _load(db, emp.id)
    audit(db, actor, "EMPLOYEE_CREATED", "employee", emp.id, new_value=_audit_view(emp))
    db.commit()
    return to_out(emp), temp_password


def update_employee(db: Session, actor: Actor, employee_id: uuid.UUID, data: EmployeeUpdate) -> EmployeeOut:
    org = actor.user.organization_id
    get_visible_employee(db, actor.user, employee_id)
    emp = _load(db, employee_id)
    _check_can_manage(actor, emp)
    before = _audit_view(emp)
    fields = data.model_fields_set
    old_role = emp.user.role

    for required in ("full_name", "email", "role", "employment_status", "is_active"):
        if required in fields and getattr(data, required) is None:
            raise AppError(422, "VALIDATION_ERROR", f"'{required}' cannot be empty.")

    is_self = emp.user_id == actor.user.id
    if is_self and ({"role", "is_active", "employment_status"} & fields):
        raise AppError(403, "FORBIDDEN", "You can't change your own role or account status.")

    if "role" in fields and data.role != old_role:
        _check_role_change_allowed(actor, old_role, data.role)
        _sync_manager_record(db, emp, old_role, data.role)
        emp.user.role = data.role
    if "email" in fields and data.email != emp.user.email:
        if _email_taken(db, data.email, except_user=emp.user_id):
            raise AppError(409, "DUPLICATE", "A user with this email already exists.")
        emp.user.email = data.email
    if "department_id" in fields:
        if data.department_id:
            get_in_org(db, Department, data.department_id, org, "Department")
        emp.department_id = data.department_id
    if "work_schedule_id" in fields:
        if data.work_schedule_id:
            get_in_org(db, WorkSchedule, data.work_schedule_id, org, "Schedule")
        emp.work_schedule_id = data.work_schedule_id
    if "manager_id" in fields:
        if data.manager_id:
            manager = _active_manager(db, org, data.manager_id)
            if manager.employee_id == emp.id:
                raise AppError(422, "VALIDATION_ERROR", "An employee can't be their own manager.")
        emp.manager_id = data.manager_id
    for simple in ("full_name", "phone", "hire_date"):
        if simple in fields:
            setattr(emp, simple, getattr(data, simple))

    access_removed = False
    if "employment_status" in fields:
        access_removed |= data.employment_status != EmploymentStatus.ACTIVE
        emp.employment_status = data.employment_status
    if "is_active" in fields:
        access_removed |= data.is_active is False
        emp.user.is_active = data.is_active
    if access_removed:
        revoke_all_for_user(db, emp.user_id, "access_removed")

    db.flush()
    emp = _load(db, employee_id)
    old, new = changed_fields(before, _audit_view(emp))
    if new:
        audit(db, actor, "EMPLOYEE_UPDATED", "employee", emp.id, old, new)
    db.commit()
    return to_out(emp)


def set_employee_locations(
    db: Session, actor: Actor, employee_id: uuid.UUID, data: LocationAssignment
) -> EmployeeOut:
    get_visible_employee(db, actor.user, employee_id)
    emp = _load(db, employee_id)
    _check_can_manage(actor, emp)
    before = _audit_view(emp)["locations"]
    _set_locations(db, actor.user.organization_id, emp, data, actor.user.id)
    db.flush()
    emp = _load(db, employee_id)
    after = _audit_view(emp)["locations"]
    if before != after:
        audit(db, actor, "EMPLOYEE_LOCATIONS_CHANGED", "employee", emp.id,
              {"locations": before}, {"locations": after})
    db.commit()
    return to_out(emp)


def reset_password(db: Session, actor: Actor, employee_id: uuid.UUID) -> str:
    get_visible_employee(db, actor.user, employee_id)
    emp = _load(db, employee_id)
    _check_can_manage(actor, emp)
    if emp.user_id == actor.user.id:
        raise AppError(422, "VALIDATION_ERROR", "Use change-password for your own account.")
    temp_password = generate_temporary_password()
    emp.user.password_hash = hash_password(temp_password)
    emp.user.must_change_password = True
    emp.user.failed_login_count = 0
    emp.user.locked_until = None
    emp.user.token_version += 1  # logs the person out everywhere
    revoke_all_for_user(db, emp.user_id, "password_reset")
    audit(db, actor, "USER_PASSWORD_RESET", "employee", emp.id)  # the password itself is never logged
    db.commit()
    return temp_password


# --- Employee's own profile -----------------------------------------------------------------


def _my_employee(db: Session, user: User) -> Employee:
    emp = db.scalar(select(Employee).where(Employee.user_id == user.id).options(*_LOADERS))
    if emp is None:
        raise AppError(404, "NOT_FOUND", "There is no employee record for this account.")
    return emp


def my_profile(db: Session, user: User) -> MyProfile:
    emp = _my_employee(db, user)
    active = [el for el in emp.locations if el.location.is_active]
    primary = next((el.location_id for el in active if el.is_primary), None)
    return MyProfile(
        employee_code=emp.employee_code,
        full_name=emp.full_name,
        email=user.email,
        phone=emp.phone,
        department=emp.department.name if emp.department else None,
        manager=_manager_name(emp.manager) if emp.manager else None,
        locations=[
            LocationBrief.model_validate(el.location)
            for el in sorted(active, key=lambda el: (not el.is_primary, el.location.name))
        ],
        primary_location_id=primary,
    )


def update_my_profile(db: Session, actor: Actor, data: MyProfileUpdate) -> MyProfile:
    emp = _my_employee(db, actor.user)
    if "phone" in data.model_fields_set and data.phone != emp.phone:
        audit(db, actor, "OWN_PROFILE_UPDATED", "employee", emp.id,
              {"phone": emp.phone}, {"phone": data.phone})
        emp.phone = data.phone
        db.commit()
    return my_profile(db, actor.user)
