"""Phone registration and HR approval (decision 11.8).

- A phone is identified by a fingerprint (hash of ANDROID_ID).
- One phone can belong to only one employee at a time -> a second employee trying to register
  the same phone is refused and a DEVICE_SHARED security event is raised.
- New phones start as PENDING_APPROVAL and can't be used for attendance until HR approves.
- Approving a new phone deactivates the employee's previous phone.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.models import DeviceRegistration, Employee
from app.models.enums import DeviceStatus, NotificationEvent, Severity
from app.schemas.common import Page, PageParams
from app.schemas.devices import DeviceOut, DeviceRegister
from app.services.audit import Actor, audit, write_security_event
from app.services.notifications import notify

IN_USE = (DeviceStatus.PENDING_APPROVAL, DeviceStatus.ACTIVE)


def to_out(device: DeviceRegistration, employee: Employee) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        employee_id=employee.id,
        employee_name=employee.full_name,
        employee_code=employee.employee_code,
        status=device.status,
        platform=device.platform,
        device_model=device.device_model,
        os_version=device.os_version,
        app_version=device.app_version,
        requested_at=device.created_at,
        approved_at=device.approved_at,
        decision_note=device.decision_note,
        last_seen_at=device.last_seen_at,
    )


def register(db: Session, actor: Actor, employee: Employee, data: DeviceRegister) -> DeviceOut:
    in_use = db.scalars(
        select(DeviceRegistration).where(
            DeviceRegistration.device_fingerprint == data.device_fingerprint,
            DeviceRegistration.status.in_(IN_USE),
        )
    ).all()
    other = next((d for d in in_use if d.employee_id != employee.id), None)
    if other is not None:
        write_security_event(
            db, event_type="DEVICE_SHARED", severity=Severity.MEDIUM,
            organization_id=employee.organization_id, user_id=actor.user.id,
            employee_id=employee.id, device_registration_id=other.id,
            ip_address=actor.info.ip_address,
            details={"registered_to_employee_id": str(other.employee_id)},
        )
        db.commit()
        raise AppError(
            409, "DEVICE_IN_USE",
            "This phone is registered to another employee. Each person must use their own phone. "
            "Contact HR if this is a mistake.",
        )

    mine = next((d for d in in_use if d.employee_id == employee.id), None)
    now = clock.now()
    if mine is not None and (mine.public_key == data.public_key or mine.status == DeviceStatus.PENDING_APPROVAL):
        # Same phone registering again (e.g. app restarted), or a request not yet approved.
        mine.install_id = data.install_id
        mine.public_key = data.public_key
        mine.key_algorithm = data.key_algorithm
        mine.app_version = data.app_version
        mine.os_version = data.os_version
        mine.device_model = data.device_model
        mine.last_seen_at = now
        db.commit()
        return to_out(mine, employee)
    if mine is not None:
        # An APPROVED phone presenting a NEW key (app reinstalled - or someone imitating the
        # phone). Never swap the trusted key silently: the old registration stops working and
        # the new key needs HR approval again.
        mine.status = DeviceStatus.REREGISTRATION_REQUIRED
        mine.decision_note = "New app key presented; waiting for HR approval of the new registration"
        audit(db, actor, "DEVICE_KEY_CHANGED", "device", mine.id,
              {"status": "ACTIVE"}, {"status": "REREGISTRATION_REQUIRED"})
        db.flush()

    device = DeviceRegistration(
        employee_id=employee.id,
        status=DeviceStatus.PENDING_APPROVAL,
        last_seen_at=now,
        **data.model_dump(),
    )
    db.add(device)
    db.flush()
    audit(db, actor, "DEVICE_REGISTRATION_REQUESTED", "device", device.id,
          new_value={"device_model": data.device_model, "os_version": data.os_version})
    notify(
        db, organization_id=employee.organization_id, employee=employee,
        event=NotificationEvent.DEVICE_APPROVAL_REQUESTED,
        title=f"New phone to approve: {employee.full_name}",
        lines=[f"{employee.full_name} registered a phone. It can't be used for attendance until HR approves it."],
        rows=[("Employee", f"{employee.full_name} ({employee.employee_code})"),
              ("Phone", data.device_model or "-"), ("Android", data.os_version or "-")],
        link="/phones", dedupe_key=f"device:{device.id}",
    )
    db.commit()
    return to_out(device, employee)


def my_devices(db: Session, employee: Employee) -> list[DeviceOut]:
    rows = db.scalars(
        select(DeviceRegistration)
        .where(DeviceRegistration.employee_id == employee.id)
        .order_by(DeviceRegistration.created_at.desc())
    )
    return [to_out(d, employee) for d in rows]


def list_devices(
    db: Session, org_id: uuid.UUID, status: DeviceStatus | None, page: PageParams
) -> Page[DeviceOut]:
    query = (
        select(DeviceRegistration, Employee)
        .join(Employee, Employee.id == DeviceRegistration.employee_id)
        .where(Employee.organization_id == org_id)
    )
    if status:
        query = query.where(DeviceRegistration.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(DeviceRegistration.created_at.desc()).offset(page.offset).limit(page.page_size)
    ).all()
    return Page(items=[to_out(d, e) for d, e in rows], total=total, page=page.page, page_size=page.page_size)


def _get(db: Session, actor: Actor, device_id: uuid.UUID) -> tuple[DeviceRegistration, Employee]:
    row = db.execute(
        select(DeviceRegistration, Employee)
        .join(Employee, Employee.id == DeviceRegistration.employee_id)
        .where(DeviceRegistration.id == device_id, Employee.organization_id == actor.user.organization_id)
        .with_for_update(of=DeviceRegistration)
    ).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Device not found.")
    return row[0], row[1]


def _decide(
    db: Session, actor: Actor, device_id: uuid.UUID, allowed_from: set[DeviceStatus],
    new_status: DeviceStatus, action: str, note: str | None,
) -> DeviceOut:
    device, employee = _get(db, actor, device_id)
    if device.status not in allowed_from:
        raise AppError(409, "INVALID_STATE", f"This device is {device.status.value}.")
    old = device.status
    now = clock.now()
    if new_status == DeviceStatus.ACTIVE:
        # Only one active phone per employee: the previous one is switched off first.
        for previous in db.scalars(
            select(DeviceRegistration).where(
                DeviceRegistration.employee_id == employee.id,
                DeviceRegistration.status == DeviceStatus.ACTIVE,
            )
        ):
            previous.status = DeviceStatus.DEACTIVATED
            previous.decision_note = "Replaced by a newly approved phone"
            audit(db, actor, "DEVICE_DEACTIVATED", "device", previous.id,
                  {"status": "ACTIVE"}, {"status": "DEACTIVATED", "reason": "replaced"})
        db.flush()
        device.approved_by = actor.user.id
        device.approved_at = now
    device.status = new_status
    device.decision_note = note
    audit(db, actor, action, "device", device.id,
          {"status": old.value}, {"status": new_status.value, "note": note})
    db.commit()
    return to_out(device, employee)


def approve(db: Session, actor: Actor, device_id: uuid.UUID, note: str | None) -> DeviceOut:
    return _decide(db, actor, device_id, {DeviceStatus.PENDING_APPROVAL}, DeviceStatus.ACTIVE,
                   "DEVICE_APPROVED", note)


def reject(db: Session, actor: Actor, device_id: uuid.UUID, note: str | None) -> DeviceOut:
    return _decide(db, actor, device_id, {DeviceStatus.PENDING_APPROVAL}, DeviceStatus.REJECTED,
                   "DEVICE_REJECTED", note)


def deactivate(db: Session, actor: Actor, device_id: uuid.UUID, note: str | None) -> DeviceOut:
    return _decide(db, actor, device_id, {DeviceStatus.ACTIVE, DeviceStatus.PENDING_APPROVAL},
                   DeviceStatus.DEACTIVATED, "DEVICE_DEACTIVATED", note)


def require_active_device(db: Session, employee: Employee, device_id: uuid.UUID) -> DeviceRegistration:
    device = db.get(DeviceRegistration, device_id)
    if device is None or device.employee_id != employee.id:
        raise AppError(403, "DEVICE_NOT_REGISTERED", "This phone is not registered. Please register it first.")
    if device.status == DeviceStatus.PENDING_APPROVAL:
        raise AppError(403, "DEVICE_PENDING_APPROVAL", "This phone is waiting for HR approval.")
    if device.status != DeviceStatus.ACTIVE:
        raise AppError(403, "DEVICE_NOT_APPROVED", "This phone can't be used for attendance. Please contact HR.")
    return device
