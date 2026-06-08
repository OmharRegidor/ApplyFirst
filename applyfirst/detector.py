"""New-job detection.

Given the RawJobs parsed from a search page, decide which are genuinely new
(by source + external_id) and persist them. To stay polite, we only fetch the
full detail page for NEW jobs — never re-fetch ones we've already seen — and
pause briefly between detail fetches.

Edited-repost detection (the UPDATED status) is intentionally deferred to a
later milestone so this stage makes at most one extra request per new job.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from applyfirst.models import RawJob
from applyfirst.sources.base import JobSource
from applyfirst.store import Store, content_hash


@dataclass(slots=True)
class DetectResult:
    new: list[RawJob] = field(default_factory=list)
    seen: int = 0
    detail_errors: int = 0


def detect_and_store(
    source: JobSource,
    store: Store,
    raw_jobs: list[RawJob],
    fetch_details: bool = True,
    max_desc_len: int = 50_000,
    detail_delay: tuple[float, float] = (0.3, 0.8),
) -> DetectResult:
    result = DetectResult()
    for raw in raw_jobs:
        if store.get_job(raw.source, raw.external_id) is not None:
            result.seen += 1
            continue

        description: str | None = None
        chash: str | None = None
        if fetch_details:
            try:
                detail = source.fetch_detail(raw)
                description = detail.description[:max_desc_len] if detail.description else None
                chash = content_hash(description) if description else None
            except Exception:
                # Never lose a new job because its detail fetch failed — store it
                # without a description; it can be re-fetched later.
                result.detail_errors += 1
            else:
                time.sleep(random.uniform(*detail_delay))  # polite gap between detail fetches

        store.insert_job(raw, content_hash=chash, raw_description=description)
        result.new.append(raw)
    return result
