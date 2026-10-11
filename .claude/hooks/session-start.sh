#!/bin/bash
# Cloud-session setup: Python venv + deps, local PostgreSQL (dev/test DBs), migrations, dashboard deps.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT/backend"

# Backend dependencies
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements-dev.txt -c constraints.txt

# Local-only secrets (gitignored), generated once
rnd() { head -c 33 /dev/urandom | base64 | tr -d '/+=\n'; }
if [ ! -f .env ]; then
  sed -e "s|^DB_OWNER_PASSWORD=.*|DB_OWNER_PASSWORD=$(rnd)|" \
      -e "s|^DB_APP_PASSWORD=.*|DB_APP_PASSWORD=$(rnd)|" \
      -e "s|^SEED_DEFAULT_PASSWORD=.*|SEED_DEFAULT_PASSWORD=$(rnd)Aa1!|" \
      -e "s|^JWT_SECRET=.*|JWT_SECRET=$(rnd)$(rnd)|" \
      -e "s|^QR_MASTER_KEY=.*|QR_MASTER_KEY=$(rnd)$(rnd)$(rnd)|" .env.example > .env
fi

# PostgreSQL (container restarts leave the cluster stopped)
PGV=$(ls /usr/lib/postgresql | sort -n | tail -1)
pg_lsclusters | grep -q online || pg_ctlcluster "$PGV" main start
for _ in $(seq 20); do su postgres -c "pg_isready -q" && break; sleep 1; done

set -a; . ./.env; set +a
# Setup SQL uses the PG17 'builtin' locale provider; fall back to C.UTF-8 on older servers.
sed -e "s/ LOCALE_PROVIDER builtin BUILTIN_LOCALE ''C.UTF-8'' LOCALE ''C''/ LOCALE ''C.UTF-8''/" \
    ../database/setup/create_local_databases.sql |
  su postgres -c "psql -q -v owner_password='$DB_OWNER_PASSWORD' -v app_password='$DB_APP_PASSWORD' -f -" >/dev/null
.venv/bin/alembic upgrade head

# Dashboard dependencies
cd "$ROOT/dashboard" && npm install --no-package-lock --no-audit --no-fund --silent

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$ROOT/backend/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
