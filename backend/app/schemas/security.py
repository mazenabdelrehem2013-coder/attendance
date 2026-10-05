"""Audit log viewer, audit-chain verification, security monitoring, alerts and data retention."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import AlertStatus, RetentionCategory, Severity

# --- Audit log --------------------------------------------------------------------------------


class AuditLogItem(BaseModel):
    id: uuid.UUID
    seq: int
    created_at: datetime
    actor: str  # email, or "System"
    actor_name: str | None
    actor_role: str | None
    action: str
    object_type: str | None
    object_id: str | None
    changed: list[str]  # names of the fields that changed
    ip_address: str | None


class AuditLogDetail(AuditLogItem):
    old_value: dict | None
    new_value: dict | None
    user_agent: str | None
    request_id: str | None
    row_hash: str
    prev_hash: str | None


class AuditLogPage(BaseModel):
    items: list[AuditLogItem]
    total: int


class AuditExportRequest(BaseModel):
    date_from: date
    date_to: date
    action: str | None = Field(None, max_length=64)
    actor_user_id: uuid.UUID | None = None
    object_type: str | None = Field(None, max_length=64)
    q: str | None = Field(None, max_length=100)


class ChainResult(BaseModel):
    ok: bool
    rows_checked: int
    last_seq: int | None
    problem: str | None
    problem_seq: int | None
    checked_at: datetime


# --- Monitoring -------------------------------------------------------------------------------


class AlertOut(BaseModel):
    id: uuid.UUID
    rule: str
    rule_label: str
    severity: Severity
    title: str
    details: dict
    employee_id: uuid.UUID | None
    employee_name: str | None
    count: int
    first_seen_at: datetime
    last_seen_at: datetime
    status: AlertStatus
    handled_by: str | None
    handled_at: datetime | None
    note: str | None


class AlertPage(BaseModel):
    items: list[AlertOut]
    total: int


class AlertAction(BaseModel):
    status: Literal["ACKNOWLEDGED", "RESOLVED"]
    note: str | None = Field(None, max_length=1000)


class RuleInfo(BaseModel):
    rule: str
    label: str
    severity: Severity
    description: str


class CountItem(BaseModel):
    key: str
    label: str | None = None
    count: int


class DayCount(BaseModel):
    date: date
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class SecurityOverview(BaseModel):
    date_from: date
    date_to: date
    total_events: int
    by_severity: dict[str, int]
    by_type: list[CountItem]
    per_day: list[DayCount]
    top_employees: list[CountItem]  # key = employee code, label = name
    failed_logins: int
    locked_accounts: int
    top_ips: list[CountItem]  # failed logins per IP address
    open_alerts: dict[str, int]  # severity -> open + acknowledged alerts
    chain: ChainResult | None  # last audit-chain verification


# --- Data retention ---------------------------------------------------------------------------


class RetentionItem(BaseModel):
    category: RetentionCategory
    label: str
    description: str
    retain_days: int
    min_days: int
    automatic: bool  # False = kept; deleting is a manual decision (attendance records)


class RetentionUpdate(BaseModel):
    retain_days: int = Field(ge=30, le=3650 * 2)


class RetentionRun(BaseModel):
    ran_at: datetime
    results: dict[str, int]  # category -> rows removed / cleared
