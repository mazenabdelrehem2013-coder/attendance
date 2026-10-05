"""Data scoping: which employees may this user see?

Every query that returns employee or attendance data must go through `employee_scope()`.

    ADMIN / HR -> every employee in their organization
    MANAGER    -> only employees whose manager is them
    EMPLOYEE   -> only themselves
"""

import uuid

from sqlalchemy import ColumnElement, false, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Employee, Manager, User
from app.models.enums import Role


def manager_id_for(db: Session, user: User) -> uuid.UUID | None:
    return db.scalar(select(Manager.id).where(Manager.user_id == user.id, Manager.is_active))


def employee_scope(db: Session, user: User) -> ColumnElement[bool]:
    """SQL condition on Employee limiting rows to what `user` may see."""
    in_org = Employee.organization_id == user.organization_id
    if user.role in (Role.ADMIN, Role.HR):
        return in_org
    if user.role == Role.MANAGER:
        manager_id = manager_id_for(db, user)
        return in_org & (Employee.manager_id == manager_id) if manager_id else false()
    return in_org & (Employee.user_id == user.id)


def get_visible_employee(db: Session, user: User, employee_id: uuid.UUID) -> Employee:
    """Load one employee, or 404 if it doesn't exist OR the user may not see it
    (same answer in both cases, so the existence of other people's records isn't revealed)."""
    employee = db.scalar(
        select(Employee).where(Employee.id == employee_id, employee_scope(db, user))
    )
    if employee is None:
        raise AppError(404, "NOT_FOUND", "Employee not found.")
    return employee

