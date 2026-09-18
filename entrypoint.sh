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

# Start the long-running poll worker.
python -m applyfirst.saas.worker &
worker_pid=$!

# If the worker ever exits, stop the machine so Fly restarts it (keeps polling alive).
( wait "$worker_pid"; echo "[entrypoint] worker exited — restarting machine" >&2; kill 1 ) &

# Web server in the foreground (becomes PID 1).
exec uvicorn applyfirst.saas.app:app --host 0.0.0.0 --port 8080 --workers 1
