"""SQLite persistence (WAL mode).

Single-user V1 store. Maps RawJob/JobDetail to rows and enforces dedupe via
UNIQUE(source, external_id). Opened with check_same_thread=False so the
background tailoring worker (added in a later milestone) can share it under WAL.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from applyfirst.models import JobStatus, RawJob

SCHEMA = """
CREATE TABLE IF NOT EXISTS job (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    employer        TEXT,
    employment_type TEXT,
    salary_text     TEXT,
    raw_description TEXT,
    posted_at       TEXT,
    scraped_at      TEXT NOT NULL,
    content_hash    TEXT,
    matched_keyword TEXT,
    status          TEXT NOT NULL DEFAULT 'DISCOVERED',
    attempts        INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_job_scraped_at ON job(scraped_at DESC);

CREATE TABLE IF NOT EXISTS saved_search (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL UNIQUE,
    active      INTEGER NOT NULL DEFAULT 1,
    baselined   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key     TEXT PRIMARY KEY,
    value   TEXT
);

-- The AI-tailored application package, persisted at email-send time so the
-- read-only dashboard can show what was sent. One current package per job.
CREATE TABLE IF NOT EXISTS tailored (
    job_id              INTEGER PRIMARY KEY REFERENCES job(id) ON DELETE CASCADE,
    application_subject TEXT,
    cover_letter        TEXT,
    screening_json      TEXT,
    package_json        TEXT,
    provider            TEXT,
    ai_available        INTEGER,
    created_at          TEXT NOT NULL
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _posted_iso(raw: RawJob) -> str | None:
    return raw.posted_at.strftime("%Y-%m-%d %H:%M:%S") if raw.posted_at else None


class Store:
    def __init__(self, path: str | Path = "applyfirst.db") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        # Wait up to 5s for a lock instead of erroring instantly — lets the
        # poller and a second reader/writer (e.g. the dashboard) coexist safely.
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        # Add columns introduced after a DB may already exist (idempotent).
        try:
            self.conn.execute(
                "ALTER TABLE saved_search ADD COLUMN baselined INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # column already present

    def close(self) -> None:
        self.conn.close()

    # --- meta (key/value): heartbeats, last-backup date, etc. ---
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        cur = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row is not None else default

    def touch_heartbeat(self) -> None:
        """Record that a poll cycle just completed (read by the `health` command)."""
        self.set_meta("last_cycle_at", utcnow_iso())

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- saved searches ---
    def add_search(self, keyword: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO saved_search(keyword, active, baselined, created_at) "
            "VALUES (?, 1, 0, ?)",
            (keyword.strip(), utcnow_iso()),
        )
        self.conn.commit()

    def active_keywords(self) -> list[str]:
        cur = self.conn.execute("SELECT keyword FROM saved_search WHERE active=1 ORDER BY id")
        return [row["keyword"] for row in cur.fetchall()]

    def is_baselined(self, keyword: str) -> bool:
        cur = self.conn.execute(
            "SELECT baselined FROM saved_search WHERE keyword=?", (keyword.strip(),)
        )
        row = cur.fetchone()
        return bool(row["baselined"]) if row is not None else False

    def set_baselined(self, keyword: str) -> None:
        self.conn.execute(
            "UPDATE saved_search SET baselined=1 WHERE keyword=?", (keyword.strip(),)
        )
        self.conn.commit()

    # --- jobs ---
    def get_job(self, source: str, external_id: str) -> sqlite3.Row | None:
        cur = self.conn.execute(
            "SELECT * FROM job WHERE source=? AND external_id=?", (source, external_id)
        )
        return cur.fetchone()

    def insert_job(
        self,
        raw: RawJob,
        content_hash: str | None = None,
        raw_description: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO job (source, external_id, url, title, employment_type, salary_text,
                             raw_description, posted_at, scraped_at, content_hash,
                             matched_keyword, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISCOVERED')
            """,
            (
                raw.source, raw.external_id, raw.url, raw.title, raw.employment_type,
                raw.salary_text, raw_description, _posted_iso(raw), utcnow_iso(),
                content_hash, raw.matched_keyword,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_status(self, job_id: int, status: JobStatus) -> None:
        self.conn.execute("UPDATE job SET status=? WHERE id=?", (status.value, job_id))
        self.conn.commit()

    def recent_jobs(self, limit: int = 30) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM job ORDER BY scraped_at DESC, id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

    def count_jobs(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM job").fetchone()[0])

    # --- tailored packages (persisted at send time; read by the dashboard) ---
    def save_tailored(self, job_id: int, result) -> None:
        """Persist the AI package for a job (upsert). `result` is a TailorResult."""
        pkg = result.package
        screening = [qa.model_dump() for qa in pkg.screening_questions]
        self.conn.execute(
            """
            INSERT INTO tailored (job_id, application_subject, cover_letter, screening_json,
                                  package_json, provider, ai_available, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                application_subject = excluded.application_subject,
                cover_letter        = excluded.cover_letter,
                screening_json      = excluded.screening_json,
                package_json        = excluded.package_json,
                provider            = excluded.provider,
                ai_available        = excluded.ai_available,
                created_at          = excluded.created_at
            """,
            (
                job_id, pkg.application_subject, pkg.cover_letter,
                json.dumps(screening, ensure_ascii=False), pkg.model_dump_json(),
                result.provider, int(bool(result.ai_available)), utcnow_iso(),
            ),
        )
        self.conn.commit()

    def get_tailored(self, job_id: int) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM tailored WHERE job_id=?", (job_id,))
        return cur.fetchone()
