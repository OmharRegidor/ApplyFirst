#!/bin/sh
# ApplyFirst V2 SaaS container entrypoint (Fly.io beta).
#
# ONE machine runs BOTH processes so they share the SQLite file on the /data volume:
#   - the poll worker (background; loops with jitter)
#   - the uvicorn web server (foreground / PID 1 after `exec`)
#
# A Fly volume attaches to a single machine, so the web + worker MUST live together here.
# When you outgrow this (M6 / Postgres), split them onto separate machines.
set -eu

# Migrate the schema once, up front, so the two processes don't race on first boot.
python - <<'PY'
from applyfirst.saas.config import load_saas_config
from applyfirst.saas import db
db.init_db(load_saas_config().db_path).close()
print("[entrypoint] schema ready")
PY

# Keep the poll worker alive. It exits when it crashes, when it cannot start (a missing master
# key, say), or on purpose when its own watchdog finds a cycle hung (exit 70). Every time, this
# loop starts it again, without touching the web server.
#
# Why a loop and not `wait`: the old version ran `( wait "$worker_pid"; ...; kill 1 ) &`, but the
# worker is a sibling of that subshell, not its child, so `wait` failed at once, `set -eu` ended
# the subshell, and nothing ever restarted a dead worker.
#
# Backoff: 10s after a failure, doubling to 5 minutes while it keeps failing fast, back to 10s
# once a run has lasted 10 minutes. A crash loop is visible in `fly logs` without flooding them.
(
  delay=10
  while :; do
    started=$(date +%s)
    status=0
    python -m applyfirst.saas.worker || status=$?
    ran=$(( $(date +%s) - started ))
    if [ "$ran" -ge 600 ]; then delay=10; fi
    echo "[entrypoint] worker exited with status $status after ${ran}s, restarting in ${delay}s" >&2
    sleep "$delay"
    if [ "$ran" -lt 600 ] && [ "$delay" -lt 300 ]; then delay=$(( delay * 2 )); fi
    if [ "$delay" -gt 300 ]; then delay=300; fi
  done
) &

# Web server in the foreground (becomes PID 1).
exec uvicorn applyfirst.saas.app:app --host 0.0.0.0 --port 8080 --workers 1
