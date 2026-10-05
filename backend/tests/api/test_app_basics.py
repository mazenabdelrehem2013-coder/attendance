"""API skeleton tests: health checks, error format, request ids, security headers, docs, CORS."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app


def _alembic_head() -> str:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.core.config import BACKEND_DIR

    return ScriptDirectory.from_config(Config(str(Path(BACKEND_DIR) / "alembic.ini"))).get_current_head()


@pytest.fixture
def client(migrated_test_db) -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


# --- Health ---------------------------------------------------------------------------------


def test_liveness(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == get_settings().app_version


def test_readiness_reports_database_and_schema_version(client):
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert body["schema_version"] == _alembic_head()


def test_readiness_returns_503_when_database_is_down(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise ConnectionError("database is down")

    client.app.dependency_overrides[get_db] = lambda: BrokenSession()
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["database"] == "unavailable"
    assert "database is down" not in r.text  # internal error text is not exposed


# --- Error format -----------------------------------------------------------------------------


def test_unknown_route_uses_standard_error_format(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    error = r.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == r.headers["X-Request-ID"]


def _app_with_test_routes() -> FastAPI:
    app = create_app()

    class Payload(BaseModel):
        latitude: float = Field(ge=-90, le=90)

    @app.post("/test/validate")
    def validate(payload: Payload):
        return {"ok": True}

    @app.get("/test/crash")
    def crash():
        raise RuntimeError("secret internal detail: password=abc")

    return app


def test_validation_errors_name_the_field_but_do_not_echo_the_value():
    client = TestClient(_app_with_test_routes(), raise_server_exceptions=False)
    r = client.post("/test/validate", json={"latitude": 123.456})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "latitude"
    assert "123.456" not in r.text


def test_broken_json_gets_a_clear_message():
    client = TestClient(_app_with_test_routes(), raise_server_exceptions=False)
    r = client.post(
        "/test/validate",
        content='{"latitude": "C:\\folder\\.env"}',  # a single backslash is invalid in JSON
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_JSON"


def test_unexpected_errors_do_not_leak_internal_details():
    client = TestClient(_app_with_test_routes(), raise_server_exceptions=False)
    r = client.get("/test/crash")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in r.text and "password" not in r.text


# --- Request id & security headers ------------------------------------------------------------


def test_request_id_is_generated(client):
    r = client.get("/api/v1/health")
    assert len(r.headers["X-Request-ID"]) == 32


def test_safe_incoming_request_id_is_reused(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"


def test_unsafe_incoming_request_id_is_replaced(client):
    r = client.get("/api/v1/health", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert r.headers["X-Request-ID"] != "<script>alert(1)</script>"


def test_security_headers_are_present(client):
    r = client.get("/api/v1/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


# --- Docs & CORS ------------------------------------------------------------------------------


def test_docs_available_outside_production(client):
    assert client.get("/docs").status_code == 200


def test_docs_disabled_in_production(monkeypatch, migrated_test_db):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()


def test_no_cors_headers_by_default(client):
    r = client.get("/api/v1/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers


def test_serves_the_dashboard_from_the_same_address(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>dashboard</html>")
    (tmp_path / "assets" / "app-1a2b.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("not for the web")
    monkeypatch.setattr(get_settings(), "static_dir", str(tmp_path))
    client = TestClient(create_app())

    page = client.get("/reports")  # a dashboard page: the app does its own routing
    assert page.status_code == 200 and "dashboard" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    asset = client.get("/assets/app-1a2b.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    api = client.get("/api/v1/nothing-here")
    assert api.status_code == 404 and api.headers["content-type"].startswith("application/json")
    assert api.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert "not for the web" not in client.get("/../secret.txt").text
    assert "not for the web" not in client.get("/%2e%2e/secret.txt").text


def test_cloud_sql_socket_address():
    from pydantic import SecretStr

    from app.core.config import _pg_url

    url = _pg_url("attendance_app", SecretStr("p@ss/word"), "/cloudsql/proj:africa-south1:db", 5432, "attendance")
    assert url == "postgresql+psycopg://attendance_app:p%40ss%2Fword@/attendance?host=/cloudsql/proj:africa-south1:db"
