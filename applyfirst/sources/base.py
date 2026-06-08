"""The JobSource seam.

V1 has one implementation (onlinejobs.ph). V2 adds more (Upwork, etc.) behind
this same protocol so the pipeline never changes. All access is public HTTP —
no login, no stored credentials.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from applyfirst.models import JobDetail, RawJob

# A normal desktop User-Agent. We identify as a browser and read politely
# (jittered interval + backoff handled by the caller) — public pages only.
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@runtime_checkable
class JobSource(Protocol):
    name: str

    def search_latest(self, keyword: str) -> list[RawJob]:
        """Return the newest jobs for a keyword (parsed from the search page)."""
        ...

    def fetch_detail(self, job: RawJob) -> JobDetail:
        """Return a job's full description (parsed from its page)."""
        ...


def make_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": DEFAULT_UA, "Accept-Language": "en-US,en;q=0.9"},
        timeout=timeout,
        follow_redirects=True,
    )
