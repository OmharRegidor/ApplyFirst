"""SaaS data layer — raw sqlite3, schema-versioned migrations.

All SQL for the SaaS lives in THIS module (and ``tenant.py``) so the eventual
Postgres migration (SYSTEM-DESIGN.md M6) is a contained rewrite, not a sprawl.

SQLite-MVP note: types are stored dialect-neutrally — UUIDs as TEXT (uuid4 strings),
timestamps as ISO-8601 UTC TEXT, the future encrypted-token columns as BLOB (NULL in
M1; populated in M2 when the gmail.send refresh token is first received).
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from applyfirst.saas import crypto

# Tables that carry per-tenant data — every query against these MUST be scoped by
# user_id (enforced via ``tenant.py``; see the CI grep guard in the M1 plan).
TENANT_TABLES = frozenset({"oauth_credentials", "user_profiles", "user_keywords"})

_SCHEMA_VERSION = 2


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


@dataclass(slots=True)
class Profile:
    user_id: str
    full_name: str
    job_type: str
    standard_subject: str
    standard_message: str
    profile_hash: str | None
    activated_at: str | None

    @property
    def is_complete(self) -> bool:
        return bool(self.full_name and self.job_type
                    and self.standard_subject and self.standard_message)

    @property
    def is_activated(self) -> bool:
        return self.activated_at is not None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Profile:
        return cls(
            user_id=row["user_id"],
            full_name=row["full_name"],
            job_type=row["job_type"],
            standard_subject=row["standard_subject"],
            standard_message=row["standard_message"],
            profile_hash=row["profile_hash"],
            activated_at=row["activated_at"],
        )


@dataclass(slots=True)
class Keyword:
    id: str
    keyword: str


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
    if version < 2:
        _migrate_v2(conn)
        conn.execute("PRAGMA user_version=2;")
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


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """M2: the 4-field onboarding profile + per-user saved-search keywords."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id                   TEXT PRIMARY KEY,
            user_id              TEXT NOT NULL UNIQUE,
            full_name            TEXT NOT NULL DEFAULT '',
            job_type             TEXT NOT NULL DEFAULT '',
            standard_subject     TEXT NOT NULL DEFAULT '',
            standard_message     TEXT NOT NULL DEFAULT '',
            profile_extras_json  TEXT,
            profile_hash         TEXT,
            activated_at         TEXT,
            updated_at           TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_keywords (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            keyword     TEXT NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            UNIQUE (user_id, keyword),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS ix_user_keywords_user_id ON user_keywords(user_id);
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


def store_gmail_credential(
    conn: sqlite3.Connection, user_id: str, *, refresh_token: str, master_key: bytes,
) -> None:
    """Envelope-encrypt the gmail.send refresh token and store it (one google row/user).

    The raw token never touches the DB — only ciphertext + iv + the encrypted DEK.
    """
    # Bind the encrypted token to its owner (AAD) so it can't be relocated to another row.
    blob = crypto.encrypt_secret(refresh_token.encode("utf-8"), master_key,
                                 aad=user_id.encode("utf-8"))
    conn.execute("DELETE FROM oauth_credentials WHERE user_id=? AND provider='google'", (user_id,))
    conn.execute(
        """
        INSERT INTO oauth_credentials
            (id, user_id, provider, refresh_token_ciphertext, refresh_token_iv,
             encrypted_dek, gmail_scope_granted, updated_at)
        VALUES (?, ?, 'google', ?, ?, ?, 1, ?)
        """,
        (_new_id(), user_id, blob.ciphertext, blob.iv, blob.encrypted_dek, _now_iso()),
    )
    conn.commit()


def gmail_connected(conn: sqlite3.Connection, user_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM oauth_credentials "
        "WHERE user_id=? AND provider='google' AND gmail_scope_granted=1 LIMIT 1",
        (user_id,),
    ).fetchone()
    return row is not None


def get_gmail_refresh_token(
    conn: sqlite3.Connection, user_id: str, master_key: bytes,
) -> str | None:
    """Decrypt and return the user's gmail.send refresh token, or None if not connected."""
    row = conn.execute(
        "SELECT refresh_token_ciphertext, refresh_token_iv, encrypted_dek "
        "FROM oauth_credentials "
        "WHERE user_id=? AND provider='google' AND gmail_scope_granted=1",
        (user_id,),
    ).fetchone()
    if row is None or row["refresh_token_ciphertext"] is None:
        return None
    blob = crypto.EnvelopeBlob(
        ciphertext=row["refresh_token_ciphertext"],
        iv=row["refresh_token_iv"],
        encrypted_dek=row["encrypted_dek"],
    )
    return crypto.decrypt_secret(blob, master_key, aad=user_id.encode("utf-8")).decode("utf-8")


def clear_gmail_credential(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute("DELETE FROM oauth_credentials WHERE user_id=? AND provider='google'", (user_id,))
    conn.commit()


# --- user_profiles -----------------------------------------------------------

def _profile_hash(full_name: str, job_type: str, subject: str, message: str) -> str:
    h = hashlib.sha256()
    for field in (full_name, job_type, subject, message):
        h.update(field.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def upsert_profile(
    conn: sqlite3.Connection, user_id: str, *,
    full_name: str, job_type: str, standard_subject: str, standard_message: str,
) -> Profile:
    """Create/refresh the 4-field profile; recompute profile_hash; preserve activation."""
    ph = _profile_hash(full_name, job_type, standard_subject, standard_message)
    conn.execute(
        """
        INSERT INTO user_profiles
            (id, user_id, full_name, job_type, standard_subject, standard_message,
             profile_hash, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            full_name = excluded.full_name,
            job_type = excluded.job_type,
            standard_subject = excluded.standard_subject,
            standard_message = excluded.standard_message,
            profile_hash = excluded.profile_hash,
            updated_at = excluded.updated_at
        """,
        (_new_id(), user_id, full_name, job_type, standard_subject, standard_message,
         ph, _now_iso()),
    )
    conn.commit()
    return get_profile(conn, user_id)


def get_profile(conn: sqlite3.Connection, user_id: str) -> Profile | None:
    row = conn.execute("SELECT * FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
    return Profile.from_row(row) if row is not None else None


def set_activated(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute(
        "UPDATE user_profiles SET activated_at=? WHERE user_id=? AND activated_at IS NULL",
        (_now_iso(), user_id),
    )
    conn.commit()


# --- user_keywords -----------------------------------------------------------

def add_keyword(conn: sqlite3.Connection, user_id: str, keyword: str) -> None:
    kw = keyword.strip()
    if not kw:
        return
    conn.execute(
        "INSERT INTO user_keywords (id, user_id, keyword, is_active, created_at) "
        "VALUES (?, ?, ?, 1, ?) ON CONFLICT(user_id, keyword) DO NOTHING",
        (_new_id(), user_id, kw, _now_iso()),
    )
    conn.commit()


def list_keywords(conn: sqlite3.Connection, user_id: str) -> list[Keyword]:
    rows = conn.execute(
        "SELECT id, keyword FROM user_keywords WHERE user_id=? AND is_active=1 ORDER BY created_at",
        (user_id,),
    ).fetchall()
    return [Keyword(id=r["id"], keyword=r["keyword"]) for r in rows]


def delete_keyword(conn: sqlite3.Connection, user_id: str, keyword_id: str) -> None:
    conn.execute(
        "DELETE FROM user_keywords WHERE id=? AND user_id=?", (keyword_id, user_id),
    )
    conn.commit()
