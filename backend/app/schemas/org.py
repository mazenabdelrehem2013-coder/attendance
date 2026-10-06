import uuid
from datetime import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.schemas.common import Code, Name


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("unknown timezone (use names like Africa/Lagos)") from None
    return value


def _round_coordinate(value):
    """Google Maps copies ~14 decimals; 6 decimals (about 10 cm) is what we store."""
    if isinstance(value, (int, float, str, Decimal)) and not isinstance(value, bool):
        try:
            return Decimal(str(value).strip()).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return value  # let the normal validation report it
    return value


Timezone = Annotated[str, AfterValidator(_valid_timezone)]
Latitude = Annotated[Decimal, BeforeValidator(_round_coordinate), Field(ge=-90, le=90, max_digits=9, decimal_places=6)]
Longitude = Annotated[Decimal, BeforeValidator(_round_coordinate), Field(ge=-180, le=180, max_digits=9, decimal_places=6)]
Radius = Annotated[int, Field(ge=10, le=5000, description="Allowed radius in meters")]
Minutes = Annotated[int, Field(ge=0, le=240)]


# --- Branches -------------------------------------------------------------------------------


class BranchCreate(BaseModel):
    name: Name
    code: Code


class BranchUpdate(BaseModel):
    name: Name | None = None
    code: Code | None = None
    is_active: bool | None = None


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str
    is_active: bool


# --- Departments ----------------------------------------------------------------------------


class DepartmentCreate(BaseModel):
    name: Name
    code: Code
    branch_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: Name | None = None
    code: Code | None = None
    branch_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str
    branch_id: uuid.UUID | None
    is_active: bool


# --- Work schedules -------------------------------------------------------------------------


class ScheduleDay(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


def _unique_weekdays(days: list[ScheduleDay]) -> list[ScheduleDay]:
    if len({d.weekday for d in days}) != len(days):
        raise ValueError("each weekday may appear only once")
    return sorted(days, key=lambda d: d.weekday)


ScheduleDays = Annotated[list[ScheduleDay], Field(min_length=1, max_length=7), AfterValidator(_unique_weekdays)]


class ScheduleCreate(BaseModel):
    name: Name
    grace_minutes: Minutes = 15
    early_departure_minutes: Minutes = 0
    days: ScheduleDays


class ScheduleUpdate(BaseModel):
    name: Name | None = None
    grace_minutes: Minutes | None = None
    early_departure_minutes: Minutes | None = None
    days: ScheduleDays | None = Field(None, description="Replaces all days when given")
    is_active: bool | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    grace_minutes: int
    early_departure_minutes: int
    is_active: bool
    days: list[ScheduleDay]


# --- Locations ------------------------------------------------------------------------------


class LocationCreate(BaseModel):
    branch_id: uuid.UUID
    name: Name
    code: Code
    address: str | None = Field(None, max_length=500)
    latitude: Latitude
    longitude: Longitude
    radius_m: Radius = 200
    timezone: Timezone = "Africa/Lagos"
    work_schedule_id: uuid.UUID | None = None


class LocationUpdate(BaseModel):
    """Only the fields you send are changed."""

    branch_id: uuid.UUID | None = None
    name: Name | None = None
    code: Code | None = None
    address: str | None = Field(None, max_length=500)
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    radius_m: Radius | None = None
    timezone: Timezone | None = None
    work_schedule_id: uuid.UUID | None = None
    is_active: bool | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    code: str
    address: str | None
    latitude: Decimal
    longitude: Decimal
    radius_m: int
    timezone: str
    work_schedule_id: uuid.UUID | None
    is_active: bool


class LocationBrief(BaseModel):
    """What an employee sees about their own assigned locations."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    address: str | None
    timezone: str
