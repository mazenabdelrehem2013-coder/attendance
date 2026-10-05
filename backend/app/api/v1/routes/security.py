"""Audit log viewer, audit-chain verification, security monitoring & alerts, data retention.
HR and Admin can see everything here; only Admin can change how long data is kept."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, require_roles
from app.db.session import get_db
from app.models import User
from app.models.enums import RetentionCategory, Role
from app.schemas.security import (
    AlertAction,
    AlertOut,
    AlertPage,
    AuditExportRequest,
    AuditLogDetail,
    AuditLogPage,
    ChainResult,
    RetentionItem,
    RetentionRun,
    RetentionUpdate,
    RuleInfo,
    SecurityOverview,
)
from app.services import audit_viewer, monitoring, retention
from app.services.audit import Actor
from app.services.monitoring import Finding, raise_alert
from app.services.team_attendance import org_today

router = APIRouter(tags=["audit & security"])
hr = require_roles(Role.HR)
hr_actor = actor_with_roles(Role.HR)
admin_actor = actor_with_roles(Role.ADMIN)


# --- Audit log --------------------------------------------------------------------------------


@router.get("/audit-logs", response_model=AuditLogPage, summary="Who changed what (newest first)")
def audit_logs(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    action: str | None = Query(None, max_length=64),
    actor_user_id: uuid.UUID | None = None,
    object_type: str | None = Query(None, max_length=64),
    object_id: str | None = Query(None, max_length=64),
    q: str | None = Query(None, max_length=100, description="Search action, object or person"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(hr),
    db: Session = Depends(get_db),
):
    return audit_viewer.list_logs(db, user, start=date_from, end=date_to, action=action, actor_user_id=actor_user_id,
                                  object_type=object_type, object_id=object_id, q=q, limit=limit, offset=offset)


@router.get("/audit-logs/actions", response_model=list[str], summary="All action names (for the filter)")
def audit_actions(user: User = Depends(hr), db: Session = Depends(get_db)):
    return audit_viewer.actions(db, user)


@router.get("/audit-logs/chain", response_model=ChainResult | None, summary="Result of the last tamper check")
def chain_status(user: User = Depends(hr), db: Session = Depends(get_db)):
    return audit_viewer.last_check(db)


@router.post("/audit-logs/verify", response_model=ChainResult, summary="Check now that no audit entry was changed or deleted")
def verify(actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    result = audit_viewer.verify_chain(db)
    if not result.ok:
        raise_alert(db, actor.user.organization_id, Finding(
            "AUDIT_TAMPERING", f"seq:{result.problem_seq}", "Audit log tampering detected", 1,
            result.checked_at, result.checked_at, {"problem": result.problem, "entry": result.problem_seq}))
    db.commit()
    return result


@router.post("/audit-logs/export", summary="Download audit entries as Excel (the export itself is recorded)")
def export(body: AuditExportRequest, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    file = audit_viewer.export(db, actor, body)
    return Response(file.content, media_type=file.media_type,
                    headers={"Content-Disposition": f'attachment; filename="{file.filename}"'})


@router.get("/audit-logs/{log_id}", response_model=AuditLogDetail, summary="One audit entry with old and new values")
def audit_log(log_id: uuid.UUID, user: User = Depends(hr), db: Session = Depends(get_db)):
    return audit_viewer.detail(db, user, log_id)


# --- Security monitoring ----------------------------------------------------------------------


@router.get("/security/overview", response_model=SecurityOverview, summary="Security dashboard numbers")
def overview(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: User = Depends(hr),
    db: Session = Depends(get_db),
):
    end = date_to or org_today(db, user)
    return monitoring.overview(db, user, date_from or end - timedelta(days=29), end)


@router.get("/security/rules", response_model=list[RuleInfo], summary="The alert rules and what they look for")
def rules(user: User = Depends(hr)):
    return monitoring.rule_list()


@router.get("/security/alerts", response_model=AlertPage, summary="Security alerts (default: not yet resolved)")
def alerts(
    status: str = Query("active", pattern="^(active|all|OPEN|ACKNOWLEDGED|RESOLVED)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(hr),
    db: Session = Depends(get_db),
):
    return monitoring.list_alerts(db, user, status, limit, offset)


@router.post("/security/alerts/{alert_id}", response_model=AlertOut, summary="Acknowledge or resolve an alert")
def handle(alert_id: uuid.UUID, body: AlertAction, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return monitoring.handle_alert(db, actor, alert_id, body)


# --- Data retention ---------------------------------------------------------------------------


@router.get("/retention", response_model=list[RetentionItem], summary="How long each kind of data is kept")
def retention_settings(user: User = Depends(hr), db: Session = Depends(get_db)):
    return retention.settings(db, user)


@router.get("/retention/last-run", response_model=RetentionRun | None, summary="Last automatic clean-up")
def retention_last_run(user: User = Depends(hr), db: Session = Depends(get_db)):
    return retention.last_run(db, user)


@router.put("/retention/{category}", response_model=RetentionItem, summary="Change a keep period (Admin only)")
def update_retention(category: RetentionCategory, body: RetentionUpdate, actor: Actor = Depends(admin_actor),
                     db: Session = Depends(get_db)):
    return retention.update_setting(db, actor, category, body)


