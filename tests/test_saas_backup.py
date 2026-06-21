"""M5 — nightly SaaS backup: local online-backup + optional env-gated remote push."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

from applyfirst.saas import backup, db


def _seeded_db(saas_cfg):
    db.init_db(saas_cfg.db_path).close()  # create the SaaS DB file


def test_run_backup_writes_local_gzip(saas_cfg, tmp_path):
    _seeded_db(saas_cfg)
    cfg = dataclasses.replace(saas_cfg, backup_dir=str(tmp_path / "bk"))
    out = backup.run_backup(cfg)
    assert out.endswith(".db.gz")
    assert Path(out).exists()


def test_run_backup_invokes_remote_when_configured(saas_cfg, tmp_path, monkeypatch):
    _seeded_db(saas_cfg)
    cfg = dataclasses.replace(saas_cfg, backup_dir=str(tmp_path / "bk"),
                              backup_remote_cmd="rclone copy {path} remote:bucket")
    calls = {}
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.update(args=args))
    backup.run_backup(cfg)
    assert calls["args"][0] == "rclone" and "copy" in calls["args"]


def test_run_backup_no_remote_means_no_subprocess(saas_cfg, tmp_path, monkeypatch):
    _seeded_db(saas_cfg)
    cfg = dataclasses.replace(saas_cfg, backup_dir=str(tmp_path / "bk"))  # remote unset
    called = {"n": 0}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.update(n=called["n"] + 1))
    backup.run_backup(cfg)
    assert called["n"] == 0


def test_run_backup_survives_remote_failure(saas_cfg, tmp_path, monkeypatch):
    _seeded_db(saas_cfg)
    cfg = dataclasses.replace(saas_cfg, backup_dir=str(tmp_path / "bk"),
                              backup_remote_cmd="rclone copy {path} remote:bucket")

    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "rclone")

    monkeypatch.setattr(subprocess, "run", boom)
    out = backup.run_backup(cfg)          # must NOT raise — local backup is preserved
    assert Path(out).exists()
