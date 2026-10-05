#!/usr/bin/env bash
# Adds per-IP flood protection to the attendance site only (CargoTrace/rewjido untouched).
# Edits the LIVE site file in place (it contains certbot's HTTPS lines), tests nginx, and puts
# the old file back if the test fails. Safe to run again.
#     sudo bash nginx-ratelimit.sh
set -euo pipefail
SITE=/etc/nginx/sites-available/attendance
ZONE=/etc/nginx/conf.d/attendance-ratelimit.conf
cp "$SITE" "$SITE.bak"
echo 'limit_req_zone $binary_remote_addr zone=attendance_api:10m rate=20r/s;' > "$ZONE"
if ! grep -q 'zone=attendance_api' "$SITE"; then
  # Only in the HTTPS server block's "location /" (the one that proxies to the API).
  sed -i '\#proxy_pass http://127.0.0.1:8100;#i\        limit_req zone=attendance_api burst=200 nodelay;\n        limit_req_status 429;' "$SITE"
fi
if nginx -t 2>&1; then
  systemctl reload nginx
  rm -f "$SITE.bak"
  echo "Rate limit active: $(grep -c 'zone=attendance_api' "$SITE") location(s)"
else
  mv "$SITE.bak" "$SITE"; rm -f "$ZONE"
  echo "nginx test failed - previous configuration restored"; exit 1
fi
