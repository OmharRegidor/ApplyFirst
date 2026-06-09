#!/usr/bin/env bash
# ApplyFirst health watchdog. Run by applyfirst-health.timer (as root).
#
# `applyfirst health` exits 0 when the run loop's last cycle is fresh, or 1 when it
# is stale / has never completed. If stale, we restart the service so a hung-but-alive
# loop recovers on its own. (A crashed process is already handled by Restart=always.)
set -uo pipefail

APP_DIR=/opt/applyfirst
PY="$APP_DIR/.venv/bin/python"

cd "$APP_DIR" || { echo "applyfirst-health: cannot cd to $APP_DIR" >&2; exit 1; }

if "$PY" -m applyfirst.cli health; then
    exit 0
fi

echo "applyfirst-health: heartbeat STALE -> restarting applyfirst.service" >&2
systemctl restart applyfirst.service
