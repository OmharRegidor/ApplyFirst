"""One poll cycle: search each keyword, detect new jobs, alert on them.

First time a keyword is polled, the current page is stored silently as a
*baseline* (no alerts) so you aren't spammed with the whole backlog. After that,
only genuinely-new jobs trigger an email.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from applyfirst.detector import detect_and_store
from applyfirst.notify.compose import build_job_email
from applyfirst.screening import detect_screening_hints


@dataclass(slots=True)
class CycleResult:
    new_total: int = 0
    emailed: int = 0
    email_errors: int = 0
    baselined: int = 0


def run_cycle(
    store,
    source,
    notifier=None,
    fetch_details: bool = True,
    verbose: bool = True,
    keyword_pause: tuple[float, float] = (1.0, 2.5),
) -> CycleResult:
    result = CycleResult()
    keywords = store.active_keywords()

    for i, keyword in enumerate(keywords):
        raw = source.search_latest(keyword)

        # First poll of this keyword: store silently as a baseline, never alert.
        if not store.is_baselined(keyword):
            res = detect_and_store(source, store, raw, fetch_details=False)
            store.set_baselined(keyword)
            result.baselined += len(res.new)
            if verbose:
                print(f"[{keyword}] baseline established: {len(res.new)} existing jobs stored "
                      f"(no alerts on first run)")
            _pause(i, keywords, keyword_pause)
            continue

        res = detect_and_store(source, store, raw, fetch_details=fetch_details)
        result.new_total += len(res.new)
        if verbose:
            extra = f" detail_errors={res.detail_errors}" if res.detail_errors else ""
            print(f"[{keyword}] fetched={len(raw)} new={len(res.new)} seen={res.seen}{extra}")

        for raw_job in res.new:
            row = store.get_job(raw_job.source, raw_job.external_id)
            if row is None:
                continue
            hints = detect_screening_hints(row["raw_description"] or "")
            if verbose:
                print(f"   + {row['posted_at'] or '?'} UTC  {row['title']}  "
                      f"[{row['employment_type'] or '-'}, {row['salary_text'] or '-'}]")
                print(f"     {row['url']}")
                if hints:
                    print(f"     📋 {len(hints)} application-instruction line(s) detected")
            if notifier is not None:
                subject, text, html = build_job_email(row, hints)
                try:
                    notifier.send(subject, text, html)
                    result.emailed += 1
                except Exception as exc:  # never let one bad send kill the cycle
                    result.email_errors += 1
                    print(f"     ! email failed: {exc}")

        _pause(i, keywords, keyword_pause)

    return result


def _pause(i: int, keywords: list[str], bounds: tuple[float, float]) -> None:
    if i < len(keywords) - 1:
        time.sleep(random.uniform(*bounds))
