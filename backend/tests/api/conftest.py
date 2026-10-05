"""Fixtures for API tests: a test client and helpers that create users in the TEST database."""

import uuid
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.session import make_session_factory
from app.main import create_app
from app.models import Employee, Organization, User
from app.models.enums import EmploymentStatus, Role

PASSWORD = "Correct-Horse-Battery-9"


@dataclass
class TestUser:
    id: uuid.UUID
    email: str
    employee_code: str | None
    password: str
    organization_id: uuid.UUID


@pytest.fixture(scope="session")
def test_session_factory(migrated_test_db):
    return make_session_factory(test=True)


@pytest.fixture(scope="session")
def test_org(test_session_factory) -> uuid.UUID:
    with test_session_factory.begin() as db:
        org = Organization(name=f"API Test Org {uuid.uuid4().hex[:6]}")
        db.add(org)
        db.flush()
        return org.id


@pytest.fixture
def make_user(test_session_factory, test_org):
    """make_user(role=Role.HR, with_employee=True, **user_fields) -> TestUser"""

    def _make(
        role: Role = Role.EMPLOYEE,
        *,
        with_employee: bool = True,
        employment_status: EmploymentStatus = EmploymentStatus.ACTIVE,
        **fields,
    ) -> TestUser:
        suffix = uuid.uuid4().hex[:8]
        email = f"{role.value.lower()}-{suffix}@example.com"
        code = f"T-{suffix.upper()}" if with_employee else None
        with test_session_factory.begin() as db:
            user = User(
                organization_id=test_org,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=role,
                must_change_password=fields.pop("must_change_password", False),
                **fields,
            )
            db.add(user)
            db.flush()
            if with_employee:
                db.add(
                    Employee(
                        organization_id=test_org,
                        user_id=user.id,
                        employee_code=code,
                        full_name=f"Test {role.value.title()}",
                        hire_date=date(2025, 1, 1),
                        employment_status=employment_status,
                    )
                )
            return TestUser(user.id, email, code, PASSWORD, test_org)

    return _make


@pytest.fixture
def client(migrated_test_db) -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


def login(client: TestClient, user: TestUser, client_type: str = "MOBILE", **kwargs):
    return client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": user.password, "client_type": client_type},
        **kwargs,
    )


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
