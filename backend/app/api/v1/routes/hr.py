"""HR / Admin: overview and charts, review of flagged attendance, security events, security
policies. Everything here is HR or Admin only."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import actor_with_roles, require_roles
from app.db.session import get_db
from app.models import User
from app.models.enums import Role
from app.schemas.hr import HrOverview, PolicyOut, PolicySet, PolicyUpdate, SecurityEventOut, TrendPoint
from app.schemas.review import ReviewDetail, ReviewFilters, ReviewPage, ReviewRequest
from app.services import hr_service, review_service
from app.services.audit import Actor
from app.services.team_attendance import org_today

router = APIRouter(tags=["hr"])
hr = require_roles(Role.HR)
hr_actor = actor_with_roles(Role.HR)


@router.get("/hr/overview", response_model=HrOverview, summary="Company-wide numbers for one day + by location/department")
def overview(day: date | None = Query(None, alias="date"), user: User = Depends(hr), db: Session = Depends(get_db)):
    return hr_service.overview(db, user, day or org_today(db, user))


@router.get("/hr/trend", response_model=list[TrendPoint], summary="Daily attendance numbers for a period (max 93 days)")
def trend(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    user: User = Depends(hr),
    db: Session = Depends(get_db),
):
    date_to = date_to or org_today(db, user)
    return hr_service.trend(db, user, date_from or date_to - timedelta(days=29), date_to)


# --- Review queue ---------------------------------------------------------------------------


@router.get("/hr/review", response_model=ReviewPage, summary="Flagged attendance waiting for HR (or reviewed / rejected)")
def review_queue(
    filters: ReviewFilters = Depends(),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(hr),
    db: Session = Depends(get_db),
):
    return review_service.list_items(db, user, filters, limit, offset)


@router.get("/hr/review/{event_id}", response_model=ReviewDetail, summary="All checks and numbers for one attempt")
def review_detail(event_id: uuid.UUID, user: User = Depends(hr), db: Session = Depends(get_db)):
    return review_service.detail(db, user, event_id)


@router.post("/hr/review/{event_id}", response_model=ReviewDetail, summary="Approve or reject a flagged attempt")
def review(event_id: uuid.UUID, body: ReviewRequest, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return review_service.review(db, actor, event_id, body.decision, body.note)


# --- Security events ------------------------------------------------------------------------


class SecurityEventPage(BaseModel):
    items: list[SecurityEventOut]
    total: int


@router.get("/security-events", response_model=SecurityEventPage)
def security_events(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    event_type: str | None = Query(None, max_length=64),
    employee_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(hr),
    db: Session = Depends(get_db),
):
    items, total = hr_service.security_events(db, user, date_from, date_to, event_type, employee_id, limit, offset)
    return SecurityEventPage(items=items, total=total)


# --- Security policies ----------------------------------------------------------------------


@router.get("/settings/attendance-policies", response_model=PolicySet)
def get_policies(user: User = Depends(hr), db: Session = Depends(get_db)):
    return hr_service.policies(db, user.organization_id)


@router.put("/settings/attendance-policies/default", response_model=PolicyOut,
            summary="Company-wide rules (used by every location without its own)")
def update_default(body: PolicyUpdate, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    return hr_service.update_policy(db, actor, None, body)


@router.put("/settings/attendance-policies/locations/{location_id}", response_model=PolicyOut,
            summary="Give one location its own rules (e.g. GPS + QR)")
def update_location(location_id: uuid.UUID, body: PolicyUpdate, actor: Actor = Depends(hr_actor),
                    db: Session = Depends(get_db)):
    return hr_service.update_policy(db, actor, location_id, body)


@router.delete("/settings/attendance-policies/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Location goes back to the company-wide rules")
def delete_location(location_id: uuid.UUID, actor: Actor = Depends(hr_actor), db: Session = Depends(get_db)):
    hr_service.delete_location_policy(db, actor, location_id)
