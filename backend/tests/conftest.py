"""Shared test setup. Tests always use the TEST database, never attendance_dev."""

import os

os.environ["APP_ENV"] = "test"  # must be set before the app is imported
os.environ["COOKIE_SECURE"] = "false"  # the test client talks plain http://testserver
os.environ["RUN_SCHEDULER_IN_API"] = "false"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.core.config import BACKEND_DIR  # noqa: E402


@pytest.fixture(scope="session")
def migrated_test_db():
    """Rebuild the test database from the migrations once per test run."""
    cfg = Config(str(Path(BACKEND_DIR) / "alembic.ini"))
    cfg.cmd_opts = type("opts", (), {"x": ["db=test"]})()  # same as `alembic -x db=test`
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


# Shared fixtures defined in other modules (e.g. the `world` test company).
pytest_plugins = ["tests.api.world"]
