#!/usr/bin/env bash
# Install a new version (a bundle made by deploy-from-pc.ps1) with automatic roll-back.
#     sudo bash deploy.sh /tmp/attendance-release.tar.gz
# Steps: unpack -> install Python packages -> database migrations -> switch -> restart -> health
# check. If the new version doesn't answer, the previous one is put back.
set -euo pipefail
BUNDLE="${1:?Give the release bundle path}"
APP=/opt/attendance
REL="$APP/releases/$(date +%Y%m%d-%H%M%S)"
PREVIOUS="$(readlink -f "$APP/current" 2>/dev/null || true)"

echo "== Unpacking into $REL"
mkdir -p "$REL"
tar -xzf "$BUNDLE" -C "$REL"
# The app can read, never change, its own code (root writes; group 'attendance' reads only).
chown -R root:attendance "$REL" && chmod -R u=rwX,g=rX,o= "$REL"

echo "== Python packages"
[ -x "$APP/venv/bin/python" ] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --disable-pip-version-check -r "$REL/backend/requirements.txt" \
  -c "$REL/backend/constraints.txt"

echo "== Database migrations"
( set -a; . /etc/attendance/jobs.env; set +a; cd "$REL/backend" && "$APP/venv/bin/alembic" upgrade head )

echo "== Switching to the new version"
ln -sfn "$REL" "$APP/current"
install -m 644 "$REL/server/attendance-api.service" "$REL/server/attendance-scheduler.service" /etc/systemd/system/
systemctl daemon-reload
systemctl restart attendance-api attendance-scheduler

for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8100/api/v1/health >/dev/null 2>&1; then
    echo "== Healthy: $(curl -fsS http://127.0.0.1:8100/api/v1/health)"
    ls -1dt "$APP"/releases/* | tail -n +6 | xargs -r rm -rf   # keep the last 5 versions
    exit 0
  fi
  sleep 2
done

echo "!! The new version did not start. Rolling back." >&2
journalctl -u attendance-api -n 30 --no-pager >&2 || true
if [ -n "$PREVIOUS" ]; then ln -sfn "$PREVIOUS" "$APP/current"; systemctl restart attendance-api attendance-scheduler; fi
exit 1
