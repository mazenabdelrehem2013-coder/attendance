"""Application settings, loaded from environment variables or backend/.env.

Secrets are never hard-coded here. Locally they come from backend/.env (git-ignored);
in Google Cloud they are injected from Secret Manager as environment variables.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _pg_url(user: str, password: SecretStr, host: str, port: int, name: str) -> str:
    credentials = f"{quote(user, safe='')}:{quote(password.get_secret_value(), safe='')}"
    if host.startswith("/"):
        # A socket folder, e.g. /cloudsql/PROJECT:REGION:INSTANCE on Cloud Run (no network port).
        return f"postgresql+psycopg://{credentials}@/{quote(name, safe='')}?host={quote(host, safe='/:')}"
    return f"postgresql+psycopg://{credentials}@{host}:{port}/{quote(name, safe='')}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"  # development | test | staging | production
    app_name: str = "Attendance API"
    app_version: str = "0.16.0"
    log_level: str = "INFO"
    # Interactive API docs (/docs). Turned off automatically in production.
    api_docs_enabled: bool = True
    # Browser origins allowed to call the API. Empty = none (the dashboard is served from the
    # same domain in production, so CORS isn't needed there). Example for local React dev:
    #   CORS_ORIGINS=["http://localhost:5173"]
    cors_origins: list[str] = []

    db_pool_size: int = 5
    db_max_overflow: int = 5

    # --- Authentication -------------------------------------------------------------------
    jwt_secret: SecretStr = SecretStr("")
    # During key rotation, tokens signed with the previous secret stay valid until they expire.
    jwt_previous_secret: SecretStr | None = None
    jwt_issuer: str = "attendance-api"
    jwt_audience: str = "attendance-clients"
    access_token_minutes: int = 15
    refresh_token_days_mobile: int = 30
    refresh_token_hours_web: int = 12
    # A refresh token reused within this many seconds is treated as a harmless double-send
    # (e.g. two app requests at once) instead of theft.
    refresh_reuse_grace_seconds: int = 20
    refresh_cookie_name: str = "refresh_token"
    # Browsers treat http://localhost as secure, so this can stay True locally.
    cookie_secure: bool = True

    max_failed_logins: int = 5
    lockout_minutes: int = 15
    # Failed logins from one IP address (any account) before that IP is slowed down.
    ip_failed_login_limit: int = 20
    ip_failed_login_window_minutes: int = 15
    password_min_length: int = 10

    # --- Anti-spoofing (Phase 8) ----------------------------------------------------------
    # Master key for rotating office QR codes; per-location keys are derived from it.
    qr_master_key: SecretStr = SecretStr("")
    # "off": integrity signal not used (local development, no Play Store build yet).
    # "google": every check-in must carry a Play Integrity token, verified with Google.
    play_integrity_mode: str = "off"
    play_integrity_package_name: str = "com.raya.attendance"
    # Token must have been created within this many seconds.
    play_integrity_max_age_s: int = 120

    # --- Scheduled reports (Phase 15) -----------------------------------------------------
    # Generated report files are kept this many days for download, then deleted.
    report_files_keep_days: int = 90
    # Run the scheduler (end-of-day close, scheduled reports, clean-up) inside the API process
    # every minute. Handy locally; in Google Cloud, Cloud Scheduler runs the job instead.
    run_scheduler_in_api: bool = False

    # Folder with the built dashboard (production image). Empty = the API only (local development
    # uses the Vite dev server for the dashboard).
    static_dir: str = ""

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "attendance_dev"
    db_test_name: str = "attendance_test"

    # Owner role: creates/changes tables (used only by migrations and maintenance jobs).
    db_owner_user: str = "attendance_owner"
    db_owner_password: SecretStr = SecretStr("")

    # App role: used by the running API. Cannot UPDATE/DELETE append-only tables.
    db_app_user: str = "attendance_app"
    db_app_password: SecretStr = SecretStr("")

    # Password given to the demo users created by the development seed script.
    seed_default_password: SecretStr = SecretStr("")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_enabled(self) -> bool:
        return self.api_docs_enabled and not self.is_production

    def owner_url(self, test: bool = False) -> str:
        name = self.db_test_name if test else self.db_name
        return _pg_url(self.db_owner_user, self.db_owner_password, self.db_host, self.db_port, name)

    def app_url(self, test: bool = False) -> str:
        name = self.db_test_name if test else self.db_name
        return _pg_url(self.db_app_user, self.db_app_password, self.db_host, self.db_port, name)


@lru_cache
def get_settings() -> Settings:
    return Settings()
