"""Core data types shared across the pipeline.

These are deliberately plain dataclasses (not ORM models). The Store layer
maps them to/from SQLite rows, keeping persistence concerns out of the
scraping/tailoring code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    """Lifecycle of a job. Status is the source of truth for crash recovery."""

    DISCOVERED = "DISCOVERED"   # found on a search page, not yet packaged
    PACKAGED = "PACKAGED"       # AI package + PDF generated
    NOTIFIED = "NOTIFIED"       # alert email sent
    VIEWED = "VIEWED"           # per-job page opened
    APPLIED = "APPLIED"         # owner marked applied (frozen)
    SKIPPED = "SKIPPED"         # owner skipped (frozen)
    UPDATED = "UPDATED"         # edited repost (re-tailor if not applied)
    FAILED = "FAILED"           # processing failed; retryable via attempts


@dataclass(slots=True)
class RawJob:
    """A job as seen on a search-results card (no full description yet)."""

    source: str
    external_id: str
    url: str
    title: str
    employment_type: str | None = None
    salary_text: str | None = None
    posted_at: datetime | None = None       # stored in UTC
    preview: str | None = None              # short blurb shown on the card
    matched_keyword: str | None = None


@dataclass(slots=True)
class JobDetail:
    """A job's full detail, fetched from its dedicated page."""

    raw: RawJob
    description: str
    skills: list[str] = field(default_factory=list)
    employer: str | None = None
