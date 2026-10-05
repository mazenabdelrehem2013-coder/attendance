import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import LeaveStatus, LeaveType
from app.schemas.common import Name


class HolidayCreate(BaseModel):
    holiday_date: date
    name: Name
    location_id: uuid.UUID | None = Field(None, description="Empty = all locations")


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    holiday_date: date
    name: str
    location_id: uuid.UUID | None


class LeaveCreate(BaseModel):
    employee_id: uuid.UUID
    leave_type: LeaveType
    start_date: date
    end_date: date
    note: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("leave can't be longer than one year")
        return self


class LeaveOut(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    status: LeaveStatus
    note: str | None
