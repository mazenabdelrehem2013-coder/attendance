r"""The scheduler: everything that happens on a timetable, in one job.

Each run ("tick"):
  1. closes yesterday for every company (missing check-outs, absences, their alerts) - once,
     after 00:15 local time
  2. creates the scheduled reports whose time has come (ready to download)
  3. deletes report files older than their keep period
  4. evaluates the security alert rules (Phase 16)
  5. once a night after 02:00: verifies the audit-log chain and runs the data-retention clean-up

Safe to run as often as you like, and on several servers at once (a database lock makes
sure only one tick runs at a time). In Google Cloud, Cloud Scheduler starts it every
5 minutes (Phase 18). Locally the API runs it every minute when RUN_SCHEDULER_IN_API=true,
or by hand:

    .venv\Scripts\python -m app.jobs.scheduler            (one tick)
    .venv\Scripts\python -m app.jobs.scheduler --loop     (every minute until Ctrl+C)
"""

import argparse
import logging
import threading
import time as time_mod
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from functools import lru_cache

from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.core import clock
from app.core.config import get_settings
from app.models import AuditCheckpoint, AuditLog, Organization
from app.services import monitoring, report_schedules, retention
from app.services.audit_viewer import verify_chain

log = logging.getLogger("app.jobs.scheduler")

CLOSE_AFTER = time(0, 15)  # local time after which yesterday is closed
NIGHTLY_AFTER = time(2, 0)  # local time after which the nightly checks run
_LOCK_ID = 7_150_001  # any fixed number, used for pg_try_advisory_lock


@dataclass
class TickResult:
    ran: bool = True
    days_closed: list[str] = field(default_factory=list)
    report_files: int = 0
    files_deleted: int = 0
    new_alerts: int = 0
    chain_ok: bool | None = None  # None = not checked in this tick
    retention_ran: bool = False


def _close_days(session_factory: sessionmaker, now: datetime) -> list[str]:
    from app.jobs.close_day import close_day

    closed = []
    with session_factory() as db:
        orgs = list(db.scalars(select(Organization).where(Organization.is_active)))
    for org in orgs:
        local = now.astimezone(ZoneInfo(org.default_timezone))
        if local.time() < CLOSE_AFTER:
            continue
        day = local.date() - timedelta(days=1)
        with session_factory() as db:
            done = db.scalar(select(AuditLog.id).where(
                AuditLog.organization_id == org.id, AuditLog.action == "DAY_CLOSED",
                AuditLog.object_id == day.isoformat()).limit(1))
            if done:
                continue
            try:
                close_day(db, org.id, day)
                closed.append(f"{org.name} {day}")
            except Exception:
                db.rollback()
                log.exception("Closing the day failed", extra={"organization": str(org.id), "day": day.isoformat()})
    return closed


@lru_cache
def _owner_factory() -> sessionmaker | None:
    """The retention clean-up needs the database OWNER role (the app role can't delete evidence)."""
    from app.db.session import make_session_factory

    settings = get_settings()
    if not settings.db_owner_password.get_secret_value():
        return None
    return make_session_factory(owner=True, test=settings.app_env == "test")


def _nightly(session_factory: sessionmaker, now: datetime, result: "TickResult") -> None:
    with session_factory() as db:
        org = db.scalar(select(Organization).where(Organization.is_active).order_by(Organization.created_at).limit(1))
        if org is None:
            return
        tz = ZoneInfo(org.default_timezone)
        local = now.astimezone(tz)
        if local.time() < NIGHTLY_AFTER:
            return
        since = datetime.combine(local.date(), NIGHTLY_AFTER, tz)
        last = db.scalar(select(func.max(AuditCheckpoint.created_at)))
        if last is None or last < since:
            chain = verify_chain(db)
            result.chain_ok = chain.ok
            if not chain.ok:
                log.critical("AUDIT CHAIN BROKEN", extra={"security_alert": True, "problem": chain.problem})
                for org_id in db.scalars(select(Organization.id).where(Organization.is_active)):
                    monitoring.raise_alert(db, org_id, monitoring.Finding(
                        "AUDIT_TAMPERING", f"seq:{chain.problem_seq}", "Audit log tampering detected", 1, now, now,
                        {"problem": chain.problem, "entry": chain.problem_seq}))
            db.commit()
        purged_today = db.scalar(select(AuditLog.id).where(
            AuditLog.organization_id == org.id, AuditLog.action == "RETENTION_PURGE",
            AuditLog.object_id == now.date().isoformat()).limit(1))
    owner = _owner_factory()
    if purged_today is None and owner is not None:
        retention.purge(owner, now)
        result.retention_ran = True


def tick(session_factory: sessionmaker, now: datetime | None = None) -> TickResult:
    now = now or clock.now()
    with session_factory() as lock_db:
        if not lock_db.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_ID}):
            return TickResult(ran=False)  # another tick is running somewhere
        try:
            result = TickResult()
            result.days_closed = _close_days(session_factory, now)
            result.report_files = report_schedules.run_due(session_factory, now)
            result.files_deleted = report_schedules.purge_old_files(session_factory)
            result.new_alerts = monitoring.run_rules(session_factory, now)
            try:
                _nightly(session_factory, now, result)
            except Exception:
                log.exception("Nightly checks failed")
            return result
        finally:
            lock_db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_ID})
            lock_db.commit()


# --- Inside the API (local development) ---------------------------------------------------

_stop = threading.Event()


def start_in_background(session_factory: sessionmaker, every_s: int = 60) -> None:
    def loop():
        log.info("Scheduler running inside the API (every %s s)", every_s)
        wait = 5  # first tick shortly after start-up
        while not _stop.wait(wait):
            wait = every_s
            try:
                tick(session_factory)
            except Exception:
                log.exception("Scheduler tick failed")

    _stop.clear()
    threading.Thread(target=loop, name="scheduler", daemon=True).start()


def stop_background() -> None:
    _stop.set()


def main() -> None:
    from app.core.config import get_settings
    from app.core.logging import configure_logging
    from app.db.session import make_session_factory

    parser = argparse.ArgumentParser(description="Run the attendance scheduler")
    parser.add_argument("--loop", action="store_true", help="keep running, one tick per minute")
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    factory = make_session_factory()
    while True:
        r = tick(factory)
        if r.ran:
            print(f"{clock.now():%H:%M:%S} closed: {', '.join(r.days_closed) or '-'} | "
                  f"report files created: {r.report_files} | old files deleted: {r.files_deleted} | "
                  f"new security alerts: {r.new_alerts}"
                  + ("" if r.chain_ok is None else f" | audit chain {'OK' if r.chain_ok else 'BROKEN'}")
                  + (" | retention clean-up done" if r.retention_ran else ""))
        else:
            print("Another scheduler is already running; skipped.")
        if not args.loop:
            break
        time_mod.sleep(60)


if __name__ == "__main__":
    main()
