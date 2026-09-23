"""Local, crash-safe SQLite backups.

Uses SQLite's online backup API (safe even while ``run`` holds the DB open in WAL
mode) to copy the database, then gzips the copy to ``backups/<name>-<stamp>.db.gz``
and prunes to the most recent ``keep`` files. Remote upload (e.g. Backblaze B2) is
a V2 ops concern; this keeps a local rolling backup with zero external deps.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


# Only files of this exact shape belong to a stem. A plain "applyfirst-*" glob would also match
# "applyfirst-saas-*", and on the Oracle VM the V1 CLI and the SaaS back up into the same folder.
_STAMP = r"\d{8}-\d{6}"
_SWEEP_AGE = 3600   # seconds: a temp file younger than this may belong to a backup still running


def _own(stem: str, tail: str) -> re.Pattern:
    return re.compile(rf"{re.escape(stem)}-{_STAMP}{tail}")


def _stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def backup_db(db_path: str | Path, backup_dir: str | Path = "backups",
              keep: int = 7, stamp: str | None = None) -> Path:
    """Back up ``db_path`` to a gzipped copy in ``backup_dir``; return its Path."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or _stamp_now()
    out = backup_dir / f"{db_path.stem}-{stamp}.db.gz"
    part = backup_dir / f".{db_path.stem}-{stamp}.db.gz.part"
    tmp = backup_dir / f".{db_path.stem}-{stamp}.tmp.db"

    _sweep(backup_dir, db_path.stem)   # leftovers from a run that was killed part-way
    _check_space(db_path, backup_dir)

    # Only a complete gzip ever carries the real name, so prune can never count a truncated
    # file as one of the backups it keeps. Every failure path removes both temporary files.
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(tmp))
        try:
            with dst:
                src.backup(dst)  # consistent online snapshot
        finally:
            dst.close()
            src.close()
        with open(tmp, "rb") as f_in, gzip.open(part, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.replace(part, out)
    finally:
        for leftover in (tmp, part, *_journals(tmp)):
            leftover.unlink(missing_ok=True)

    _prune(backup_dir, db_path.stem, keep)
    return out


def _journals(db_file: Path) -> list[Path]:
    return [db_file.with_name(db_file.name + suffix) for suffix in ("-journal", "-wal", "-shm")]


def _sweep(backup_dir: Path, stem: str) -> None:
    """Remove temporary files a killed backup left behind. Their leading dot keeps them out of
    prune, so without this each one would hold its space on the disk forever.

    Only this stem's own names, and only files over an hour old, so a second backup running at
    the same moment (the Oracle timer and a manual run, say) never loses its in-flight files.
    Best effort: a file another process holds open on Windows is left for next time."""
    own = re.compile(rf"\.{re.escape(stem)}-{_STAMP}\.(tmp\.db(-journal|-wal|-shm)?|db\.gz\.part)")
    cutoff = time.time() - _SWEEP_AGE
    for leftover in backup_dir.iterdir():
        if not own.fullmatch(leftover.name):
            continue
        try:
            if leftover.stat().st_mtime < cutoff:
                leftover.unlink(missing_ok=True)
        except OSError:
            pass


def _check_space(db_path: Path, backup_dir: Path) -> None:
    """Refuse early when the disk cannot hold the uncompressed copy plus its gzip. Better a clear
    error than filling the disk the live database shares (on Fly it is the same volume)."""
    need = 2 * db_path.stat().st_size
    free = shutil.disk_usage(backup_dir).free
    if free < need:
        raise OSError(f"not enough free disk for a backup: need about {need // 2**20} MB, "
                      f"{free // 2**20} MB free in {backup_dir}")


def _prune(backup_dir: Path, stem: str, keep: int) -> None:
    if keep <= 0:
        return
    own = _own(stem, r"\.db\.gz")
    files = sorted(p for p in backup_dir.iterdir() if own.fullmatch(p.name))  # lexical == chronological
    for old in files[:-keep]:
        old.unlink(missing_ok=True)
