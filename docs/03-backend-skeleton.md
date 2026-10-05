# Phase 3 — FastAPI Backend Skeleton

## What was built

| File | Purpose |
|---|---|
| `backend/app/main.py` | Creates the app: logging, middleware, error handlers, `/api/v1` routes |
| `backend/app/core/config.py` | All settings from `backend/.env` / environment (docs, CORS, DB pool) |
| `backend/app/core/logging.py` | One JSON line per log entry (Cloud Logging reads `severity`/`message`) |
| `backend/app/core/middleware.py` | Request ID on every request/response, access log with duration, security headers |
| `backend/app/core/errors.py` | One error format `{"error": {code, message, request_id, details}}`; internal errors never leak |
| `backend/app/db/session.py` | Database connection pool + `get_db` (one session per request, as the limited app role) |
| `backend/app/api/v1/routes/health.py` | `GET /api/v1/health` (process alive) and `GET /api/v1/health/ready` (database reachable + schema version) |
| `backend/Dockerfile`, `.dockerignore` | Production image for Cloud Run (built in the cloud in Phase 18) |
| `backend/tests/api/test_app_basics.py` | 13 API tests |

Design note: the API uses **synchronous** SQLAlchemy sessions (FastAPI runs them in a thread pool). At ~500 employees this is more than fast enough, simpler, and avoids async-driver problems on Windows.

## Run the API

All commands in **PowerShell**:

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Leave that window open (it is the running server; `Ctrl+C` stops it). Then open in your browser:

| URL | Expected |
|---|---|
| http://localhost:8000/api/v1/health | `{"status":"ok","version":"0.3.0","environment":"development"}` |
| http://localhost:8000/api/v1/health/ready | `{"status":"ok","database":"ok","schema_version":"0002"}` |
| http://localhost:8000/docs | Interactive API documentation (Swagger). Click an endpoint → **Try it out** → **Execute** |
| http://localhost:8000/api/v1/nothing | `{"error":{"code":"NOT_FOUND",...}}` — the standard error format |

The PowerShell window shows one JSON log line per request.

## Run the tests

In a **second** PowerShell window:

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest
```

Expected: `31 passed` (18 database + 13 API).

## Troubleshooting

| Problem | Fix |
|---|---|
| `[Errno 10048] ... address already in use` | Something already uses port 8000 (maybe a server from earlier). Close that window, or use `--port 8001`. |
| `/health/ready` returns `"database":"unavailable"` | PostgreSQL service stopped → Win+R → `services.msc` → start `postgresql-x64-18`. |
| `No module named uvicorn` / `fastapi` | Run the `pip install -r requirements-dev.txt` line above. |
| `/docs` page is blank | It loads its styling from the internet (cdn.jsdelivr.net); check your connection/proxy. The API itself still works. |
