import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Name


class QrDisplayCreate(BaseModel):
    location_id: uuid.UUID
    display_label: Name = Field(description="e.g. 'Reception screen'")
    rotation_seconds: int = Field(30, ge=15, le=300)


class QrDisplayOut(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    location_name: str
    display_label: str
    rotation_seconds: int
    is_active: bool
    last_heartbeat_at: datetime | None


class QrDisplayWithKey(QrDisplayOut):
    display_key: str = Field(description="Shown ONCE. Enter it on the office screen.")


class QrCurrentCode(BaseModel):
    location_name: str
    token: str = Field(description="Show this as a QR code")
    expires_at: datetime
    rotation_seconds: int
