"""Nightly SaaS database backup (M5).

Reuses the V1 online-backup core (``applyfirst.backup.backup_db``: SQLite ``.backup`` →
gzip → rolling prune, WAL-safe, zero deps) against the **SaaS** DB. An optional, env-gated
remote push (``APPLYFIRST_BACKUP_REMOTE``) ships the gzipped snapshot off-box once the owner
configures rclone/aws/b2 — inert otherwise.

Run it (the systemd backup timer calls this):
    python -m applyfirst.saas.backup
"""

from __future__ import annotations

import logging
import shlex
import subprocess

from applyfirst import log
from applyfirst.backup import backup_db
from applyfirst.saas.config import SaaSConfig, load_saas_config

_LOG = log.get_logger("saas.backup")
_REMOTE_TIMEOUT = 300  # seconds — a stuck upload must not wedge the nightly timer


def run_backup(cfg: SaaSConfig) -> str:
    """Back up the SaaS DB locally; push off-box if a remote command is configured."""
    out = backup_db(cfg.db_path, cfg.backup_dir, cfg.backup_keep)
    log.event(_LOG, "backup_written", path=str(out))

    if cfg.backup_remote_cmd:
        cmd = cfg.backup_remote_cmd.replace("{path}", str(out))
        try:
            subprocess.run(shlex.split(cmd), check=True, timeout=_REMOTE_TIMEOUT)
            log.event(_LOG, "backup_remote_pushed", path=str(out))
        except Exception as exc:  # noqa: BLE001 — a failed push must not lose the local backup
            log.event(_LOG, "backup_remote_failed", level=logging.ERROR, error=str(exc)[:200])

    return str(out)


def main() -> int:
    run_backup(load_saas_config())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
