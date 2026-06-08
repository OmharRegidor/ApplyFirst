"""onlinejobs.ph job source.

Detection and full descriptions are public — proven in the Phase-0 spike. We
fetch the search page per keyword (already sorted newest-first) and the job
detail pages with plain HTTP, then parse with selectolax.

The pure ``parse_search`` / ``parse_detail`` functions take HTML strings so they
can be unit-tested against saved fixtures with no network.
"""

from __future__ import annotations

import html as _htmllib
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from selectolax.parser import HTMLParser

from applyfirst.models import JobDetail, RawJob
from applyfirst.sources.base import make_client

BASE_URL = "https://www.onlinejobs.ph"
SEARCH_PATH = "/jobseekers/jobsearch"
SOURCE_NAME = "onlinejobs.ph"

_ID_RE = re.compile(r"-(\d+)/?$")          # trailing numeric id in a job URL
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]+")
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(r"</(p|div|li|h[1-6])\s*>", re.IGNORECASE)


class OnlineJobsPHSource:
    """Public-HTTP source for onlinejobs.ph."""

    name = SOURCE_NAME

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or make_client()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OnlineJobsPHSource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def search_latest(self, keyword: str) -> list[RawJob]:
        url = f"{BASE_URL}{SEARCH_PATH}?jobkeyword={quote(keyword)}"
        resp = self._client.get(url)
        resp.raise_for_status()
        jobs = parse_search(resp.text)
        for job in jobs:
            job.matched_keyword = keyword
        return jobs

    def fetch_detail(self, job: RawJob) -> JobDetail:
        resp = self._client.get(job.url)
        resp.raise_for_status()
        return parse_detail(resp.text, job)


# --------------------------------------------------------------------------- #
# Pure parsers (no network) — unit-tested against fixtures
# --------------------------------------------------------------------------- #

def _abs_url(href: str) -> str:
    return href if href.startswith("http") else f"{BASE_URL}{href}"


def _extract_id(href: str) -> str | None:
    m = _ID_RE.search(href)
    return m.group(1) if m else None


def _find_job_href(box) -> str | None:
    """Locate the job URL for a card.

    HTML5 parsing reparents the block ``<div class="jobpost-cat-box">`` out of
    its inline wrapping ``<a>``, so the anchor ends up as the box's *previous
    sibling* (right before any whitespace/comment nodes), not its parent.
    """
    node = box.prev
    hops = 0
    while node is not None and hops < 6:
        if node.tag == "a":
            href = node.attributes.get("href") or ""
            if "/jobseekers/job/" in href:
                return href
        node = node.prev
        hops += 1
    return None


def _parse_posted(box) -> datetime | None:
    p = box.css_first("p[data-temp-2]")
    if p is None:
        for cand in box.css("p"):
            if cand.attributes.get("data-temp-2") or cand.attributes.get("data-temp"):
                p = cand
                break
    if p is None:
        return None
    raw = p.attributes.get("data-temp-2") or p.attributes.get("data-temp")
    if not raw:
        return None
    try:
        # data-temp-2 is UTC ("YYYY-MM-DD HH:MM:SS")
        return datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_search(html: str) -> list[RawJob]:
    """Parse a search-results page into RawJobs (deduped by id, order preserved)."""
    tree = HTMLParser(html)
    jobs: list[RawJob] = []
    seen: set[str] = set()

    for box in tree.css("div.jobpost-cat-box"):
        href = _find_job_href(box)
        if not href:
            continue
        ext_id = _extract_id(href)
        if not ext_id or ext_id in seen:
            continue
        seen.add(ext_id)

        title = ""
        emp_type: str | None = None
        h4 = box.css_first("h4")
        if h4 is not None:
            badge = h4.css_first("span.badge")
            emp_type = badge.text(strip=True) if badge is not None else None
            title = h4.text(deep=True, strip=True) or ""
            if emp_type:
                title = title.replace(emp_type, " ")
            title = _WS_RE.sub(" ", title).strip()

        salary = box.css_first("dd")
        desc = box.css_first("div.desc")

        jobs.append(
            RawJob(
                source=SOURCE_NAME,
                external_id=ext_id,
                url=_abs_url(href),
                title=title,
                employment_type=emp_type,
                salary_text=salary.text(strip=True) if salary is not None else None,
                posted_at=_parse_posted(box),
                preview=desc.text(strip=True) if desc is not None else None,
            )
        )
    return jobs


def _html_to_text(node) -> str:
    """Convert a description node's HTML to clean multi-line text.

    <br> and closing block tags become newlines; remaining tags (including
    onlinejobs' <ojfilter> word wrappers) are stripped, keeping their inner text.
    Done with regex rather than selectolax ``.text()``, which collapses the
    newlines we need to separate the buried "TO APPLY" instructions.
    """
    raw = node.html or ""
    raw = _BR_RE.sub("\n", raw)
    raw = _BLOCK_END_RE.sub("\n", raw)
    text = _htmllib.unescape(_TAG_RE.sub("", raw)).replace("\xa0", " ")
    out: list[str] = []
    blanks = 0
    for line in text.splitlines():
        line = line.strip()
        if line:
            blanks = 0
            out.append(line)
        else:
            blanks += 1
            if blanks <= 1:
                out.append("")
    return "\n".join(out).strip()


def parse_detail(html: str, job: RawJob) -> JobDetail:
    tree = HTMLParser(html)
    desc_node = tree.css_first("#job-description")
    description = _html_to_text(desc_node) if desc_node is not None else ""

    skills: list[str] = []
    for a in tree.css("a"):
        href = a.attributes.get("href") or ""
        if "/jobseekers/search/c/" in href:
            label = a.text(strip=True)
            if label and label not in skills:
                skills.append(label)

    return JobDetail(raw=job, description=description, skills=skills)
