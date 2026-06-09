"""Local, crash-safe SQLite backups.

Uses SQLite's online backup API (safe even while ``run`` holds the DB open in WAL
mode) to copy the database, then gzips the copy to ``backups/<name>-<stamp>.db.gz``
and prunes to the most recent ``keep`` files. Remote upload (e.g. Backblaze B2) is
a V2 ops concern; this keeps a local rolling backup with zero external deps.
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


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
    tmp = backup_dir / f".{db_path.stem}-{stamp}.tmp.db"

    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(tmp))
    try:
        with dst:
            src.backup(dst)  # consistent online snapshot
    finally:
        dst.close()
        src.close()

    try:
        with open(tmp, "rb") as f_in, gzip.open(out, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    finally:
        tmp.unlink(missing_ok=True)

    _prune(backup_dir, db_path.stem, keep)
    return out


def _prune(backup_dir: Path, stem: str, keep: int) -> None:
    if keep <= 0:
        return
    files = sorted(backup_dir.glob(f"{stem}-*.db.gz"))  # lexical == chronological for our stamp
    for old in files[:-keep]:
        old.unlink(missing_ok=True)
