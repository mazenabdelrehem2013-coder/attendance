#!/usr/bin/env bash
# Switch Google Play Integrity checking of check-ins on or off.
#     sudo bash /opt/attendance/current/server/play-integrity.sh on
#     sudo bash /opt/attendance/current/server/play-integrity.sh off
# "on": every check-in must carry a genuine Play Integrity token. Modified apps, rooted or emulated
# phones and copies not installed from Google Play are flagged for HR review (security policy
# "on_integrity_fail"). Only switch on when employees install the app from Google Play.
set -euo pipefail
case "${1:-}" in
  on) MODE=google ;;
  off) MODE=off ;;
  *) echo "Usage: play-integrity.sh on|off"; exit 2 ;;
esac
FILE=/etc/attendance/integrity.env
[ -f "$FILE" ] || { echo "$FILE is missing (Play Integrity key not installed)"; exit 1; }
sed -i "s/^PLAY_INTEGRITY_MODE=.*/PLAY_INTEGRITY_MODE=$MODE/" "$FILE"
systemctl restart attendance-api
for i in $(seq 1 15); do
  curl -fsS http://127.0.0.1:8100/api/v1/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8100/api/v1/health && echo
echo "Play Integrity checking is now: $MODE"
