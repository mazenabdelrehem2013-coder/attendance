"""Database engine and sessions.

The API uses synchronous SQLAlchemy sessions: FastAPI runs normal `def` endpoints in a thread
pool, which comfortably handles ~500 employees and avoids async database driver problems on
Windows during development.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Engine for the API, connecting as the limited app role."""
    settings = get_settings()
    return create_engine(
        settings.app_url(test=settings.app_env == "test"),
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=1800,
    )


@lru_cache
def _api_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = _api_session_factory()()
    try:
        yield db
    finally:
        db.close()


def make_session_factory(*, owner: bool = False, test: bool = False) -> sessionmaker:
    """For scripts (seed, jobs). owner=True connects as the table owner."""
    settings = get_settings()
    url = settings.owner_url(test=test) if owner else settings.app_url(test=test)
    return sessionmaker(bind=create_engine(url, pool_pre_ping=True), expire_on_commit=False)
