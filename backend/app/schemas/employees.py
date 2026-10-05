import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EmploymentStatus, Role
from app.schemas.common import Code, Email, Name, Phone
from app.schemas.org import LocationBrief


class Ref(BaseModel):
    id: uuid.UUID
    name: str


class AssignedLocation(BaseModel):
    location_id: uuid.UUID
    name: str
    is_primary: bool


class EmployeeOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    employee_code: str
    full_name: str
    email: str
    phone: str | None
    role: Role
    is_active: bool
    employment_status: EmploymentStatus
    hire_date: date | None
    department: Ref | None
    manager: Ref | None
    work_schedule_id: uuid.UUID | None
    locations: list[AssignedLocation]


class LocationAssignment(BaseModel):
    location_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    primary_location_id: uuid.UUID | None = Field(
        None, description="Defaults to the first location in the list"
    )

    @model_validator(mode="after")
    def _check(self):
        if len(set(self.location_ids)) != len(self.location_ids):
            raise ValueError("location_ids contains duplicates")
        if self.primary_location_id is None:
            self.primary_location_id = self.location_ids[0]
        elif self.primary_location_id not in self.location_ids:
            raise ValueError("primary_location_id must be one of location_ids")
        return self


class EmployeeCreate(LocationAssignment):
    full_name: Name
    employee_code: Code
    email: Email
    phone: Phone | None = None
    role: Role = Role.EMPLOYEE
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = Field(None, description="id from GET /managers")
    work_schedule_id: uuid.UUID | None = Field(
        None, description="Only if different from the location's schedule"
    )
    hire_date: date | None = None


class EmployeeCreated(BaseModel):
    employee: EmployeeOut
    temporary_password: str = Field(
        description="Shown once. Give it to the employee; they must change it at first login."
    )


class EmployeeUpdate(BaseModel):
    """Only the fields you send are changed. Send null to clear department/manager/schedule/phone."""

    full_name: Name | None = None
    email: Email | None = None
    phone: Phone | None = None
    role: Role | None = None
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    work_schedule_id: uuid.UUID | None = None
    hire_date: date | None = None
    employment_status: EmploymentStatus | None = None
    is_active: bool | None = Field(None, description="false = login disabled")


class PasswordReset(BaseModel):
    temporary_password: str


class ManagerOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    employee_id: uuid.UUID | None
    name: str
    email: str
    team_size: int


class MyProfile(BaseModel):
    employee_code: str
    full_name: str
    email: str
    phone: str | None
    department: str | None
    manager: str | None
    locations: list[LocationBrief]
    primary_location_id: uuid.UUID | None


class MyProfileUpdate(BaseModel):
    """Employees may change only their phone number. Any other field is refused."""

    model_config = ConfigDict(extra="forbid")
    phone: Phone | None = None
