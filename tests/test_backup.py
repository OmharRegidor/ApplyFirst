"""Tests for local gzipped SQLite backups."""

from __future__ import annotations

import gzip
import sqlite3

import pytest

from applyfirst.backup import backup_db


def _make_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    conn.close()


def test_backup_creates_valid_gzipped_sqlite(tmp_path):
    db = tmp_path / "applyfirst.db"
    _make_db(db)
    out = backup_db(db, backup_dir=tmp_path / "backups", keep=7)
    assert out.exists()
    assert out.name.endswith(".db.gz")
    raw = gzip.decompress(out.read_bytes())
    assert raw[:16] == b"SQLite format 3\x00"  # valid SQLite header


def test_prune_keeps_only_last_n(tmp_path):
    db = tmp_path / "applyfirst.db"
    _make_db(db)
    bdir = tmp_path / "backups"
    for i in range(5):
        backup_db(db, backup_dir=bdir, keep=3, stamp=f"2026010{i}-000000")
    remaining = sorted(p.name for p in bdir.glob("applyfirst-*.db.gz"))
    assert len(remaining) == 3
    assert remaining == [
        "applyfirst-20260102-000000.db.gz",
        "applyfirst-20260103-000000.db.gz",
        "applyfirst-20260104-000000.db.gz",
    ]


def test_missing_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_db(tmp_path / "nope.db", backup_dir=tmp_path / "b")
