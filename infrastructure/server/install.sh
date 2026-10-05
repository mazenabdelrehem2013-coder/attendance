#!/usr/bin/env bash
# ONE-TIME installation of the Raya attendance system on the (shared) Debian 13 server.
# Leaves CargoTrace and rewjido untouched. Run as root:
#     sudo DOMAIN=raya.34.35.174.159.nip.io bash install.sh
# Safe to run again (it only adds what is missing; existing secrets are kept).
set -euo pipefail
: "${DOMAIN:?Set DOMAIN, e.g. raya.34.35.174.159.nip.io}"
HERE="$(cd "$(dirname "$0")" && pwd)"
APP=/opt/attendance
ETC=/etc/attendance

echo "== 1. Packages (PostgreSQL, Python venv, PDF fonts)"
apt-get update -q
apt-get install -y -q --no-install-recommends postgresql python3-venv fonts-dejavu-core curl

echo "== 2. A dedicated system user and folders"
id attendance >/dev/null 2>&1 || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin attendance
mkdir -p "$APP/releases" "$ETC" /var/backups/attendance
chown root:attendance "$ETC" && chmod 750 "$ETC"
chmod 700 /var/backups/attendance

echo "== 3. Secrets (generated here, never shown, never leave the server)"
gen() { openssl rand -base64 64 | tr -dc 'A-Za-z0-9' | cut -c1-"$1"; }
if [ ! -f "$ETC/secrets.env" ]; then
  ( umask 077
    { echo "DB_OWNER_PASSWORD=$(gen 32)"; echo "DB_APP_PASSWORD=$(gen 32)"
      echo "JWT_SECRET=$(gen 48)"; echo "QR_MASTER_KEY=$(gen 48)"; } > "$ETC/secrets.env" )
fi
set -a; . "$ETC/secrets.env"; set +a

COMMON="APP_ENV=production
LOG_LEVEL=INFO
DB_HOST=localhost
DB_PORT=5432
DB_NAME=attendance
DB_OWNER_USER=attendance_owner
DB_APP_USER=attendance_app
DB_APP_PASSWORD=$DB_APP_PASSWORD
JWT_SECRET=$JWT_SECRET
QR_MASTER_KEY=$QR_MASTER_KEY
PLAY_INTEGRITY_MODE=off
RUN_SCHEDULER_IN_API=false
STATIC_DIR=$APP/current/static"
# The API does NOT get the owner password (it can't delete evidence). Only the jobs do.
( umask 027; echo "$COMMON" > "$ETC/api.env"
  { echo "$COMMON"; echo "DB_OWNER_PASSWORD=$DB_OWNER_PASSWORD"; } > "$ETC/jobs.env" )
chown root:attendance "$ETC/api.env" "$ETC/jobs.env"
chmod 640 "$ETC/api.env" "$ETC/jobs.env"

echo "== 4. Database (local only, not reachable from the internet)"
systemctl enable --now postgresql
sudo -u postgres --preserve-env=DB_OWNER_PASSWORD,DB_APP_PASSWORD \
  psql -q -d postgres < "$HERE/create_production_database.sql"   # read by root, passed in

echo "== 5. Services"
install -m 644 "$HERE/attendance-api.service" "$HERE/attendance-scheduler.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable attendance-api attendance-scheduler

echo "== 6. Web address $DOMAIN (nginx + free Let's Encrypt certificate)"
echo 'limit_req_zone $binary_remote_addr zone=attendance_api:10m rate=20r/s;' > /etc/nginx/conf.d/attendance-ratelimit.conf
sed "s/__DOMAIN__/$DOMAIN/g" "$HERE/nginx-attendance.conf" > /etc/nginx/sites-available/attendance
ln -sf /etc/nginx/sites-available/attendance /etc/nginx/sites-enabled/attendance
nginx -t && systemctl reload nginx
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --no-eff-email --redirect
fi

echo "== 7. Nightly database backup (14 days kept on the server)"
install -m 750 "$HERE/attendance-backup.sh" /usr/local/bin/attendance-backup.sh
echo "30 1 * * * root /usr/local/bin/attendance-backup.sh >> /var/log/attendance-backup.log 2>&1" \
  > /etc/cron.d/attendance-backup

echo "Installation done. Next: deploy.sh with a release bundle."
