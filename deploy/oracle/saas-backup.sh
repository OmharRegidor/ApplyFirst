#!/usr/bin/env bash
# Nightly SaaS DB backup — online .backup + gzip + rolling prune (+ optional remote push).
# Invoked by applyfirst-saas-backup.timer; runs unprivileged as the 'applyfirst' user.
set -uo pipefail

APP_DIR=/opt/applyfirst
PY="$APP_DIR/.venv/bin/python"

cd "$APP_DIR" || exit 1
exec "$PY" -m applyfirst.saas.backup
