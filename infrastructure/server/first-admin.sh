#!/usr/bin/env bash
# ONE-TIME: create the company and its first ADMIN account (after the first deploy).
#     sudo ORG_NAME=Raya ADMIN_EMAIL=you@example.com bash first-admin.sh
# The temporary password is generated here and stored ONLY in a root-readable file:
#     sudo cat /etc/attendance/initial-admin-password
# It must be changed at the first login. Running this again changes nothing.
set -euo pipefail
: "${ORG_NAME:?}" "${ADMIN_EMAIL:?}"
FILE=/etc/attendance/initial-admin-password
if [ ! -f "$FILE" ]; then
  ( umask 077; openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | cut -c1-16 > "$FILE" )
fi
set -a; . /etc/attendance/api.env; set +a
export ORG_NAME ADMIN_EMAIL INITIAL_ADMIN_PASSWORD="$(cat "$FILE")"
cd /opt/attendance/current/backend
# runuser keeps the environment: the password is never on a command line.
runuser -u attendance -- /opt/attendance/venv/bin/python -m app.jobs.create_admin
