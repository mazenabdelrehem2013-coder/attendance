"""Database tests: schema, constraints and the append-only / tamper-evidence protections."""

import uuid
from datetime import date

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

import app.models  # noqa: F401
from app.db.base import Base
from app.models import (
    Attendance,
    AttendanceEvent,
    AttendanceSession,
    AuditLog,
    DeviceRegistration,
    Location,
    User,
)
from app.models.enums import (
    AttendanceAction,
    DeviceStatus,
    EventResult,
    Role,
    SessionStatus,
)
from tests.db.conftest import make_org_with_employee, now


def _event(emp, loc, action=AttendanceAction.CHECK_IN) -> AttendanceEvent:
    return AttendanceEvent(
        employee_id=emp.id,
        event_type=action,
        client_request_id=uuid.uuid4(),
        server_received_at=now(),
        latitude=loc.latitude,
        longitude=loc.longitude,
        accuracy_m=12,
        location_id=loc.id,
        distance_m=15,
        result=EventResult.ACCEPTED,
    )


def _audit(org_id, action="TEST_ACTION") -> AuditLog:
    return AuditLog(organization_id=org_id, actor_role="SYSTEM", action=action, new_value={"x": 1})


# --- Schema ------------------------------------------------------------------------------


def test_all_tables_exist(owner_engine):
    tables = set(inspect(owner_engine).get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert len(Base.metadata.tables) == 34  # + report_files (15), security_alerts, audit_checkpoints (16)


def test_migrations_match_models(owner_engine):
    with owner_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models and migrations differ: {diff}"


# --- Constraints --------------------------------------------------------------------------


def test_email_is_unique_ignoring_case(owner_db):
    org, _, _ = make_org_with_employee(owner_db)
    owner_db.add(User(organization_id=org.id, email="Same@Example.com", password_hash="x", role=Role.HR))
    owner_db.flush()
    owner_db.add(User(organization_id=org.id, email="same@example.com", password_hash="x", role=Role.HR))
    with pytest.raises(IntegrityError):
        owner_db.flush()


def test_location_radius_must_be_reasonable(owner_db):
    _, loc, _ = make_org_with_employee(owner_db)
    loc.radius_m = 0
    with pytest.raises(IntegrityError):
        owner_db.flush()


def test_one_attendance_row_per_employee_per_day(owner_db):
    _, _, emp = make_org_with_employee(owner_db)
    owner_db.add(Attendance(employee_id=emp.id, attendance_date=date(2026, 10, 5)))
    owner_db.flush()
    owner_db.add(Attendance(employee_id=emp.id, attendance_date=date(2026, 10, 5)))
    with pytest.raises(IntegrityError):
        owner_db.flush()


def test_duplicate_client_request_id_is_rejected(owner_db):
    _, loc, emp = make_org_with_employee(owner_db)
    first = _event(emp, loc)
    owner_db.add(first)
    owner_db.flush()
    dup = _event(emp, loc)
    dup.client_request_id = first.client_request_id
    owner_db.add(dup)
    with pytest.raises(IntegrityError):
        owner_db.flush()


def test_only_one_open_session_per_employee(owner_db):
    _, loc, emp = make_org_with_employee(owner_db)
    day = Attendance(employee_id=emp.id, attendance_date=date(2026, 10, 5))
    e1, e2 = _event(emp, loc), _event(emp, loc)
    owner_db.add_all([day, e1, e2])
    owner_db.flush()
    owner_db.add(AttendanceSession(attendance_id=day.id, employee_id=emp.id,
                                   check_in_event_id=e1.id, check_in_at=now()))
    owner_db.flush()
    owner_db.add(AttendanceSession(attendance_id=day.id, employee_id=emp.id,
                                   check_in_event_id=e2.id, check_in_at=now()))
    with pytest.raises(IntegrityError):
        owner_db.flush()


def test_several_closed_sessions_per_day_are_allowed(owner_db):
    _, loc, emp = make_org_with_employee(owner_db)
    day = Attendance(employee_id=emp.id, attendance_date=date(2026, 10, 5))
    events = [_event(emp, loc) for _ in range(3)]
    owner_db.add_all([day, *events])
    owner_db.flush()
    for ev in events:
        owner_db.add(AttendanceSession(attendance_id=day.id, employee_id=emp.id,
                                       check_in_event_id=ev.id, check_in_at=now(),
                                       check_out_at=now(), status=SessionStatus.CLOSED))
    owner_db.flush()


def test_one_phone_cannot_be_bound_to_two_employees(owner_db):
    org, _, emp1 = make_org_with_employee(owner_db)
    _, _, emp2 = make_org_with_employee(owner_db)
    phone = "a" * 64
    owner_db.add(DeviceRegistration(employee_id=emp1.id, device_fingerprint=phone,
                                    install_id="i1", status=DeviceStatus.ACTIVE))
    owner_db.flush()
    owner_db.add(DeviceRegistration(employee_id=emp2.id, device_fingerprint=phone,
                                    install_id="i2", status=DeviceStatus.PENDING_APPROVAL))
    with pytest.raises(IntegrityError):
        owner_db.flush()


def test_deactivated_phone_can_be_registered_by_someone_else(owner_db):
    _, _, emp1 = make_org_with_employee(owner_db)
    _, _, emp2 = make_org_with_employee(owner_db)
    phone = "b" * 64
    owner_db.add(DeviceRegistration(employee_id=emp1.id, device_fingerprint=phone,
                                    install_id="i1", status=DeviceStatus.DEACTIVATED))
    owner_db.add(DeviceRegistration(employee_id=emp2.id, device_fingerprint=phone,
                                    install_id="i2", status=DeviceStatus.PENDING_APPROVAL))
    owner_db.flush()


# --- Append-only & tamper evidence ---------------------------------------------------------


def test_audit_log_cannot_be_updated_or_deleted_even_by_owner(owner_db):
    org, _, _ = make_org_with_employee(owner_db)
    owner_db.add(_audit(org.id))
    owner_db.flush()
    for sql in ("UPDATE audit_logs SET action = 'HACKED'", "DELETE FROM audit_logs"):
        with pytest.raises(DBAPIError, match="append-only"):
            with owner_db.begin_nested():
                owner_db.execute(text(sql))


def test_attendance_events_cannot_be_modified(owner_db):
    _, loc, emp = make_org_with_employee(owner_db)
    ev = _event(emp, loc)
    owner_db.add(ev)
    owner_db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        with owner_db.begin_nested():
            owner_db.execute(text("UPDATE attendance_events SET result = 'ACCEPTED', distance_m = 1"))


def test_audit_log_rows_form_a_valid_hash_chain(owner_db):
    org, _, _ = make_org_with_employee(owner_db)
    for i in range(3):
        owner_db.add(_audit(org.id, action=f"STEP_{i}"))
        owner_db.flush()
    rows = owner_db.execute(text("""
        SELECT seq, prev_hash, row_hash,
               audit_log_hash(prev_hash, seq, id, organization_id, actor_user_id, action,
                              object_type, object_id, old_value, new_value, created_at) AS recomputed
        FROM audit_logs ORDER BY seq
    """)).all()
    assert len(rows) >= 3
    for prev, row in zip(rows, rows[1:]):
        assert row.prev_hash == prev.row_hash
        assert row.seq == prev.seq + 1
    assert all(r.row_hash == r.recomputed for r in rows)


def test_retention_job_can_purge_when_explicitly_enabled(owner_db):
    org, _, _ = make_org_with_employee(owner_db)
    owner_db.add(_audit(org.id))
    owner_db.flush()
    owner_db.execute(text("SET LOCAL app.allow_purge = 'on'"))
    deleted = owner_db.execute(text("DELETE FROM audit_logs WHERE action = 'TEST_ACTION'")).rowcount
    assert deleted >= 1


# --- App role permissions --------------------------------------------------------------------


def test_app_role_can_insert_audit_logs_but_not_delete_them(app_db):
    org, _, _ = make_org_with_employee(app_db)
    app_db.add(_audit(org.id))
    app_db.flush()
    with pytest.raises(ProgrammingError, match="permission denied"):
        with app_db.begin_nested():
            app_db.execute(text("DELETE FROM audit_logs"))


def test_app_role_cannot_bypass_with_purge_flag(app_db):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with app_db.begin_nested():
            app_db.execute(text("SET LOCAL app.allow_purge = 'on'"))
            app_db.execute(text("DELETE FROM security_events"))


def test_app_role_cannot_change_schema(app_db):
    with pytest.raises(ProgrammingError, match="permission denied|must be owner"):
        with app_db.begin_nested():
            app_db.execute(text("ALTER TABLE locations ADD COLUMN hacked int"))


def test_app_role_can_read_and_write_normal_tables(app_db):
    _, loc, _ = make_org_with_employee(app_db)
    loc.radius_m = 300
    app_db.flush()
    assert app_db.scalar(select(Location.radius_m).where(Location.id == loc.id)) == 300
