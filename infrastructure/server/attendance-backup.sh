#!/usr/bin/env bash
# Nightly backup of the attendance database (cron, 01:30 server time). Keeps 14 days in
# /var/backups/attendance (readable by root only). Restore: see docs/18-deployment.md.
set -euo pipefail
DIR=/var/backups/attendance
FILE="$DIR/attendance-$(date +%Y-%m-%d).dump"
umask 077
sudo -u postgres pg_dump --format=custom --compress=6 attendance > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
find "$DIR" -name 'attendance-*.dump' -mtime +14 -delete
echo "$(date -Is) backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
