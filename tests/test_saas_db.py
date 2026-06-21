"""M1 — data layer: migrations, user upsert idempotency, FK enforcement."""

from __future__ import annotations

import sqlite3

import pytest

from applyfirst.saas import db
from applyfirst.saas.tenant import tenant_scope


def test_migrate_sets_version_and_tables(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db._SCHEMA_VERSION
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "oauth_credentials"} <= tables
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path):
    path = str(tmp_path / "x.db")
    db.init_db(path).close()
    conn = db.init_db(path)  # run again — must not error or duplicate
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db._SCHEMA_VERSION
    finally:
        conn.close()


def test_upsert_user_idempotent_by_google_sub(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        a = db.upsert_user_by_google(conn, google_sub="sub1", email="a@x.com", display_name="A")
        b = db.upsert_user_by_google(conn, google_sub="sub1", email="new@x.com", display_name="A2")
        assert a.id == b.id                 # same row, no duplicate
        assert b.email == "new@x.com"       # email refreshed on return visit
        assert b.display_name == "A2"
        assert a.plan == "free"
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_foreign_key_enforced_on_oauth_credentials(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_oauth_credential(conn, "no-such-user")
    finally:
        conn.close()


def test_get_user_missing_returns_none(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        assert db.get_user(conn, "nope") is None
    finally:
        conn.close()


def test_migrate_refuses_newer_db(tmp_path):
    path = str(tmp_path / "x.db")
    conn = db.init_db(path)
    conn.execute("PRAGMA user_version=99;")
    conn.commit()
    conn.close()

    conn2 = db.connect(path)
    try:
        with pytest.raises(RuntimeError):
            db.migrate(conn2)
        # version must be left untouched — never silently downgraded
        assert conn2.execute("PRAGMA user_version").fetchone()[0] == 99
    finally:
        conn2.close()


def test_connection_pragmas_are_set(tmp_path):
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_tenant_scope_rejects_non_tenant_table(tmp_path):
    """The TENANT_TABLES allow-list IS the SQL-injection guard — prove it bites."""
    conn = db.init_db(str(tmp_path / "x.db"))
    try:
        with tenant_scope(conn, "uid") as scope:
            with pytest.raises(ValueError):
                scope.fetch_by_id("users", "x")     # users is not tenant-scoped
            with pytest.raises(ValueError):
                scope.list("users")
    finally:
        conn.close()
