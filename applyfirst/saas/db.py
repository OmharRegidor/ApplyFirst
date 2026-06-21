"""SaaS data layer — raw sqlite3, schema-versioned migrations.

All SQL for the SaaS lives in THIS module (and ``tenant.py``) so the eventual
Postgres migration (SYSTEM-DESIGN.md M6) is a contained rewrite, not a sprawl.

SQLite-MVP note: types are stored dialect-neutrally — UUIDs as TEXT (uuid4 strings),
timestamps as ISO-8601 UTC TEXT, the future encrypted-token columns as BLOB (NULL in
M1; populated in M2 when the gmail.send refresh token is first received).
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Tables that carry per-tenant data — every query against these MUST be scoped by
# user_id (enforced via ``tenant.py``; see the CI grep guard in the M1 plan).
TENANT_TABLES = frozenset({"oauth_credentials"})

_SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass(slots=True)
class User:
    id: str
    google_sub: str
    email: str
    display_name: str | None
    plan: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> User:
        return cls(
            id=row["id"],
            google_sub=row["google_sub"],
            email=row["email"],
            display_name=row["display_name"],
            plan=row["plan"],
            created_at=row["created_at"],
        )


def connect(db_path: str) -> sqlite3.Connection:
    """Open the SaaS DB with the pragmas both the web and worker processes need."""
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")   # ride out web+worker write contention
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Apply migrations up to the current schema version (PRAGMA user_version).

    Refuses to touch a database stamped NEWER than this code understands (a rolled-back
    binary must never re-run old migrations against a forward schema), and bumps the
    version only when a migration actually runs — never unconditionally.
    """
    version = conn.execute("PRAGMA user_version;").fetchone()[0]
    if version > _SCHEMA_VERSION:
        raise RuntimeError(
            f"SaaS DB schema version {version} is newer than this code supports "
            f"({_SCHEMA_VERSION}); upgrade the application — do not downgrade the DB."
        )
    if version < 1:
        _migrate_v1(conn)
        conn.execute("PRAGMA user_version=1;")
    # future: if version < 2: _migrate_v2(conn); conn.execute("PRAGMA user_version=2;")
    conn.commit()


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            google_sub    TEXT NOT NULL UNIQUE,
            email         TEXT NOT NULL,
            display_name  TEXT,
            plan          TEXT NOT NULL DEFAULT 'free',
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS oauth_credentials (
            id                        TEXT PRIMARY KEY,
            user_id                   TEXT NOT NULL,
            provider                  TEXT NOT NULL DEFAULT 'google',
            -- envelope-encrypted gmail.send refresh token (populated in M2; NULL in M1)
            refresh_token_ciphertext  BLOB,
            refresh_token_iv          BLOB,
            refresh_token_tag         BLOB,
            encrypted_dek             BLOB,
            gmail_scope_granted       INTEGER NOT NULL DEFAULT 0,
            access_token_expiry       TEXT,
            updated_at                TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS ix_oauth_credentials_user_id
            ON oauth_credentials(user_id);
        """
    )


def init_db(db_path: str) -> sqlite3.Connection:
    """Connect + migrate. Caller owns closing the returned connection."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    migrate(conn)
    return conn


# --- users -------------------------------------------------------------------

def upsert_user_by_google(
    conn: sqlite3.Connection,
    *,
    google_sub: str,
    email: str,
    display_name: str | None,
) -> User:
    """Insert a user on first sign-in; on return-visit refresh email/display_name.

    Keyed on the Google subject id (stable, never the email).
    """
    conn.execute(
        """
        INSERT INTO users (id, google_sub, email, display_name, plan, created_at)
        VALUES (?, ?, ?, ?, 'free', ?)
        ON CONFLICT(google_sub) DO UPDATE SET
            email = excluded.email,
            display_name = excluded.display_name
        """,
        (_new_id(), google_sub, email, display_name, _now_iso()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
    ).fetchone()
    return User.from_row(row)


def get_user(conn: sqlite3.Connection, user_id: str) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User.from_row(row) if row is not None else None


# --- oauth_credentials -------------------------------------------------------

def insert_oauth_credential(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    provider: str = "google",
    gmail_scope_granted: bool = False,
) -> str:
    """Create an oauth_credentials row (token columns NULL until M2). Returns its id.

    Used now to give M1 a tenant-scoped resource to prove isolation against; reused
    by M2 when the gmail.send refresh token is actually stored (encrypted).
    """
    cred_id = _new_id()
    conn.execute(
        """
        INSERT INTO oauth_credentials (id, user_id, provider, gmail_scope_granted, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cred_id, user_id, provider, 1 if gmail_scope_granted else 0, _now_iso()),
    )
    conn.commit()
    return cred_id
