# Production image for Google Cloud Run: the API + the built web dashboard, one address.
# Built by Google Cloud Build (no Docker needed on your PC):
#   gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/attendance/app:VERSION .

# --- 1. Build the dashboard (static files) ---------------------------------------------------
FROM node:22-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --cache /tmp/npm-cache --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# --- 2. The API ------------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STATIC_DIR=/app/static

WORKDIR /app

# Fonts with full Latin coverage (e.g. Yoruba/Igbo letters such as ẹ, ọ, ṣ) for PDF reports.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/alembic.ini .
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=dashboard /dashboard/dist ./static

# Never run as root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# Cloud Run provides $PORT (default 8080). --proxy-headers: trust Google's front end for the
# real client IP (security events, login throttling).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
