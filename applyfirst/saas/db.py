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
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from applyfirst.saas import crypto

# Tables that carry per-tenant data — every query against these MUST be scoped by
# user_id (enforced via ``tenant.py``; see the CI grep guard in the M1 plan).
# jobs / tailoring_cache / worker_keyword_state / worker_meta are deliberately NOT here:
# they have no user_id (cross-tenant pool / internal worker state); the user boundary is
# enforced at the user_job_alerts join.
TENANT_TABLES = frozenset({
    "oauth_credentials", "user_profiles", "user_keywords",
    "user_job_alerts", "ai_usage",
})

_SCHEMA_VERSION = 4


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
    if version < 3:
        _migrate_v3(conn)
        conn.execute("PRAGMA user_version=3;")
    if version < 4:
        _migrate_v4(conn)
        conn.execute("PRAGMA user_version=4;")
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


# === M3: the worker's data layer ============================================

def _migrate_v3(conn: sqlite3.Connection) -> None:
    """M3: cross-tenant job pool, per-user alert fan-out, AI daily cap, tailoring cache."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id               TEXT PRIMARY KEY,
            onlinejobs_id    TEXT NOT NULL UNIQUE,   -- source external_id; global dedupe key
            title            TEXT NOT NULL,
            url              TEXT NOT NULL,
            employment_type  TEXT,
            salary_text      TEXT,
            posted_at        TEXT,
            raw_description  TEXT,
            scraped_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_job_alerts (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            job_id      TEXT NOT NULL,
            keyword     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','sent','failed','capped','skipped')),
            last_error  TEXT,
            attempts    INTEGER NOT NULL DEFAULT 0,
            sent_at     TEXT,
            created_at  TEXT NOT NULL,
            UNIQUE (user_id, job_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (job_id)  REFERENCES jobs(id)  ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ai_usage (
            user_id         TEXT NOT NULL,
            day             TEXT NOT NULL,             -- 'YYYY-MM-DD' UTC
            tailoring_calls INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tailoring_cache (
            id            TEXT PRIMARY KEY,
            job_id        TEXT NOT NULL,
            profile_hash  TEXT NOT NULL,
            package_json  TEXT NOT NULL,              -- the full TailoredPackage as JSON
            provider      TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL,
            UNIQUE (job_id, profile_hash),
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS worker_keyword_state (
            keyword       TEXT PRIMARY KEY,
            baselined_at  TEXT,
            last_polled   TEXT
        );

        CREATE TABLE IF NOT EXISTS worker_meta (
            key    TEXT PRIMARY KEY,
            value  TEXT
        );

        CREATE INDEX IF NOT EXISTS ix_alerts_status ON user_job_alerts(status);
        CREATE INDEX IF NOT EXISTS ix_alerts_user   ON user_job_alerts(user_id);
        CREATE INDEX IF NOT EXISTS ix_alerts_job    ON user_job_alerts(job_id);
        CREATE INDEX IF NOT EXISTS ix_jobs_scraped  ON jobs(scraped_at);
        """
    )


def _migrate_v4(conn: sqlite3.Connection) -> None:
    """M5: a shared fixed-window rate-limit counter for /auth/* (no user_id — keyed by IP)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS auth_rate_hits (
            bucket   TEXT PRIMARY KEY,   -- "<ip>|<window_index>"
            hits     INTEGER NOT NULL,
            expires  REAL NOT NULL       -- epoch seconds; rows pruned past this
        );
        """
    )


@dataclass(slots=True)
class Job:
    id: str
    onlinejobs_id: str
    title: str
    url: str
    employment_type: str | None
    salary_text: str | None
    posted_at: str | None
    raw_description: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Job:
        return cls(
            id=row["id"], onlinejobs_id=row["onlinejobs_id"], title=row["title"],
            url=row["url"], employment_type=row["employment_type"],
            salary_text=row["salary_text"], posted_at=row["posted_at"],
            raw_description=row["raw_description"],
        )

    def as_email_job(self, keyword: str) -> dict:
        """The mapping shape applyfirst.notify.compose.build_tailored_email expects."""
        return {
            "title": self.title, "url": self.url,
            "employment_type": self.employment_type, "salary_text": self.salary_text,
            "posted_at": self.posted_at, "matched_keyword": keyword,
        }


@dataclass(slots=True)
class Alert:
    id: str
    user_id: str
    job_id: str
    keyword: str
    status: str
    attempts: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Alert:
        return cls(id=row["id"], user_id=row["user_id"], job_id=row["job_id"],
                   keyword=row["keyword"], status=row["status"], attempts=row["attempts"])


# --- jobs --------------------------------------------------------------------

def get_job_id(conn: sqlite3.Connection, onlinejobs_id: str) -> str | None:
    row = conn.execute("SELECT id FROM jobs WHERE onlinejobs_id=?", (onlinejobs_id,)).fetchone()
    return row["id"] if row is not None else None


def insert_job(conn: sqlite3.Connection, *, onlinejobs_id: str, title: str, url: str,
               employment_type: str | None, salary_text: str | None,
               posted_at: str | None, raw_description: str | None) -> str:
    """Insert a new job (dedupe by onlinejobs_id). Returns the job id (new or existing)."""
    conn.execute(
        """
        INSERT INTO jobs (id, onlinejobs_id, title, url, employment_type, salary_text,
                          posted_at, raw_description, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(onlinejobs_id) DO NOTHING
        """,
        (_new_id(), onlinejobs_id, title, url, employment_type, salary_text,
         posted_at, raw_description, _now_iso()),
    )
    conn.commit()
    return get_job_id(conn, onlinejobs_id)


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return Job.from_row(row) if row is not None else None


# --- keyword fan-out ---------------------------------------------------------

def active_keywords_all(conn: sqlite3.Connection) -> list[str]:
    """Distinct keywords that at least one ACTIVATED user is actively watching."""
    rows = conn.execute(
        """
        SELECT DISTINCT k.keyword
        FROM user_keywords k
        JOIN user_profiles p ON p.user_id = k.user_id
        WHERE k.is_active = 1 AND p.activated_at IS NOT NULL
        ORDER BY k.keyword
        """
    ).fetchall()
    return [r["keyword"] for r in rows]


def users_for_keyword(conn: sqlite3.Connection, keyword: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT k.user_id
        FROM user_keywords k
        JOIN user_profiles p ON p.user_id = k.user_id
        WHERE k.is_active = 1 AND k.keyword = ? AND p.activated_at IS NOT NULL
        """,
        (keyword,),
    ).fetchall()
    return [r["user_id"] for r in rows]


def insert_alert(conn: sqlite3.Connection, user_id: str, job_id: str, keyword: str) -> None:
    conn.execute(
        "INSERT INTO user_job_alerts (id, user_id, job_id, keyword, status, created_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?) ON CONFLICT(user_id, job_id) DO NOTHING",
        (_new_id(), user_id, job_id, keyword, _now_iso()),
    )
    conn.commit()


def pending_alerts(conn: sqlite3.Connection) -> list[Alert]:
    rows = conn.execute(
        "SELECT * FROM user_job_alerts WHERE status='pending' ORDER BY created_at"
    ).fetchall()
    return [Alert.from_row(r) for r in rows]


def mark_alert(conn: sqlite3.Connection, alert_id: str, status: str, *,
               last_error: str | None = None, sent_at: str | None = None) -> None:
    conn.execute(
        "UPDATE user_job_alerts SET status=?, last_error=?, sent_at=? WHERE id=?",
        (status, last_error, sent_at, alert_id),
    )
    conn.commit()


def bump_attempts(conn: sqlite3.Connection, alert_id: str) -> None:
    conn.execute("UPDATE user_job_alerts SET attempts = attempts + 1 WHERE id=?", (alert_id,))
    conn.commit()


# --- daily cap ---------------------------------------------------------------

def try_increment_ai_usage(conn: sqlite3.Connection, user_id: str, cap: int) -> bool:
    """Atomically reserve one tailoring slot for today. False if at/over cap."""
    if cap <= 0:
        return False
    day = _now_iso()[:10]
    cur = conn.execute(
        """
        INSERT INTO ai_usage (user_id, day, tailoring_calls)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, day) DO UPDATE SET tailoring_calls = tailoring_calls + 1
            WHERE ai_usage.tailoring_calls < ?
        RETURNING tailoring_calls
        """,
        (user_id, day, cap),
    )
    row = cur.fetchone()
    conn.commit()
    return row is not None


def get_ai_usage_today(conn: sqlite3.Connection, user_id: str) -> int:
    """Today's tailoring-call count for a user (read-only; 0 when no row).

    Mirrors ``try_increment_ai_usage``'s day-keying exactly so the dashboard banner
    matches what the worker enforces.
    """
    day = _now_iso()[:10]
    row = conn.execute(
        "SELECT tailoring_calls FROM ai_usage WHERE user_id=? AND day=?", (user_id, day)
    ).fetchone()
    return int(row[0]) if row else 0


# --- /auth rate limiting (M5) ------------------------------------------------

def record_auth_hit(conn: sqlite3.Connection, ip: str, limit: int, window: int,
                    *, now: float | None = None) -> bool:
    """Count one /auth/* hit for ``ip`` in the current fixed window; return True if allowed.

    A single shared counter (works across the 4 uvicorn workers) using the same atomic
    INSERT…ON CONFLICT…RETURNING idiom as the daily cap. Expired buckets are pruned
    opportunistically so the table stays tiny.
    """
    if limit <= 0:
        return True
    now = time.time() if now is None else now
    win = int(now // window)
    bucket = f"{ip}|{win}"
    expires = (win + 2) * window      # keep one extra window before pruning
    cur = conn.execute(
        "INSERT INTO auth_rate_hits (bucket, hits, expires) VALUES (?, 1, ?) "
        "ON CONFLICT(bucket) DO UPDATE SET hits = hits + 1 RETURNING hits",
        (bucket, expires),
    )
    hits = cur.fetchone()[0]
    conn.execute("DELETE FROM auth_rate_hits WHERE expires < ?", (now,))
    conn.commit()
    return hits <= limit


# --- tailoring cache ---------------------------------------------------------

def cache_get(conn: sqlite3.Connection, job_id: str, profile_hash: str) -> dict | None:
    row = conn.execute(
        "SELECT package_json, provider FROM tailoring_cache WHERE job_id=? AND profile_hash=?",
        (job_id, profile_hash),
    ).fetchone()
    return {"package_json": row["package_json"], "provider": row["provider"]} if row else None


def cache_put(conn: sqlite3.Connection, job_id: str, profile_hash: str,
              package_json: str, provider: str) -> None:
    conn.execute(
        "INSERT INTO tailoring_cache (id, job_id, profile_hash, package_json, provider, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(job_id, profile_hash) DO NOTHING",
        (_new_id(), job_id, profile_hash, package_json, provider, _now_iso()),
    )
    conn.commit()


def purge_tailoring_cache(conn: sqlite3.Connection, *, keep_days: int = 30) -> None:
    """Drop cache rows older than retention or whose profile_hash is no longer referenced."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute("DELETE FROM tailoring_cache WHERE created_at < ?", (cutoff,))
    conn.execute(
        "DELETE FROM tailoring_cache WHERE profile_hash NOT IN "
        "(SELECT profile_hash FROM user_profiles WHERE profile_hash IS NOT NULL)"
    )
    conn.commit()


# --- keyword baseline state + worker heartbeat -------------------------------

def is_keyword_baselined(conn: sqlite3.Connection, keyword: str) -> bool:
    row = conn.execute(
        "SELECT baselined_at FROM worker_keyword_state WHERE keyword=?", (keyword,)
    ).fetchone()
    return row is not None and row["baselined_at"] is not None


def mark_keyword_polled(conn: sqlite3.Connection, keyword: str, *, baselined: bool) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO worker_keyword_state (keyword, baselined_at, last_polled)
        VALUES (?, ?, ?)
        ON CONFLICT(keyword) DO UPDATE SET
            last_polled = excluded.last_polled,
            baselined_at = COALESCE(worker_keyword_state.baselined_at, excluded.baselined_at)
        """,
        (keyword, now if baselined else None, now),
    )
    conn.commit()


def set_worker_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO worker_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_worker_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM worker_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row is not None else None
