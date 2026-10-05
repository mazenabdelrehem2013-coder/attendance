"""Office QR displays (HR) and the endpoint the office screen polls for the current code."""

import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, require_roles
from app.db.session import get_db
from app.models import Location, QrSession, User
from app.models.enums import Role
from app.schemas.qr import QrCurrentCode, QrDisplayCreate, QrDisplayOut, QrDisplayWithKey
from app.services import qr_service
from app.services.audit import Actor

router = APIRouter(tags=["qr"])
hr_actor = actor_with_roles(Role.HR)


def _out(display: QrSession, location: Location) -> QrDisplayOut:
    return QrDisplayOut(
        id=display.id, location_id=location.id, location_name=location.name,
        display_label=display.display_label, rotation_seconds=display.rotation_seconds,
        is_active=display.is_active, last_heartbeat_at=display.last_heartbeat_at,
    )


def _with_key(display: QrSession, location: Location, key: str) -> QrDisplayWithKey:
    return QrDisplayWithKey(**_out(display, location).model_dump(), display_key=key)


@router.get("/qr-displays", response_model=list[QrDisplayOut])
def list_displays(user: User = Depends(require_roles(Role.HR)), db: Session = Depends(get_db)):
    return [_out(d, l) for d, l in qr_service.list_displays(db, user.organization_id)]


@router.post("/qr-displays", response_model=QrDisplayWithKey, status_code=status.HTTP_201_CREATED,
             summary="Register an office screen; returns its display key once")
def create_display(body: QrDisplayCreate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return _with_key(*qr_service.create_display(db, actor, body.location_id, body.display_label,
                                                body.rotation_seconds))


@router.post("/qr-displays/{display_id}/rotate-key", response_model=QrDisplayWithKey,
             summary="New display key (old key and codes stop working)")
def rotate_key(display_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return _with_key(*qr_service.rotate_key(db, actor, display_id))


@router.post("/qr-displays/{display_id}/disable", response_model=QrDisplayOut)
def disable(display_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return _out(*qr_service.set_active(db, actor, display_id, False))


@router.post("/qr-displays/{display_id}/enable", response_model=QrDisplayOut)
def enable(display_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return _out(*qr_service.set_active(db, actor, display_id, True))


@router.get("/qr/current", response_model=QrCurrentCode,
            summary="For the office screen: the code to show now (header X-Display-Key)")
def current_code(x_display_key: str | None = Header(None), db: Session = Depends(get_db)):
    display, location, token, expires = qr_service.current_code(db, x_display_key)
    return QrCurrentCode(location_name=location.name, token=token, expires_at=expires,
                         rotation_seconds=display.rotation_seconds)
