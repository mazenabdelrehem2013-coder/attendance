"""Fixtures for database tests. They run against the TEST database (DB_TEST_NAME), which is
rebuilt from the migrations at the start of the test run. The dev database is never touched."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Branch,
    Employee,
    Location,
    Organization,
    User,
)
from app.models.enums import Role


@pytest.fixture(scope="session")
def owner_engine(migrated_test_db):
    engine = create_engine(get_settings().owner_url(test=True))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(migrated_test_db):
    engine = create_engine(get_settings().app_url(test=True))
    yield engine
    engine.dispose()


@pytest.fixture
def owner_db(owner_engine):
    """Session as the owner role. Everything is rolled back after each test."""
    with owner_engine.connect() as conn:
        trans = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        trans.rollback()


@pytest.fixture
def app_db(app_engine):
    """Session as the API's limited app role. Rolled back after each test."""
    with app_engine.connect() as conn:
        trans = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        trans.rollback()


def make_org_with_employee(db: Session) -> tuple[Organization, Location, Employee]:
    suffix = uuid.uuid4().hex[:8]
    org = Organization(name=f"Test Org {suffix}")
    db.add(org)
    db.flush()
    branch = Branch(organization_id=org.id, name="Test Branch", code="TB")
    db.add(branch)
    db.flush()
    loc = Location(
        organization_id=org.id,
        branch_id=branch.id,
        name="Test Office",
        code="TO",
        latitude=Decimal("6.428100"),
        longitude=Decimal("3.421900"),
        radius_m=200,
    )
    user = User(
        organization_id=org.id,
        email=f"user-{suffix}@example.com",
        password_hash="not-a-real-hash",
        role=Role.EMPLOYEE,
    )
    db.add_all([loc, user])
    db.flush()
    emp = Employee(
        organization_id=org.id,
        user_id=user.id,
        employee_code=f"T-{suffix}",
        full_name="Test Employee",
        hire_date=date(2025, 1, 1),
    )
    db.add(emp)
    db.flush()
    return org, loc, emp


def now() -> datetime:
    return datetime.now(UTC)
