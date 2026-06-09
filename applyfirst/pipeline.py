"""One poll cycle: search each keyword, detect new jobs, alert on them.

First time a keyword is polled, the current page is stored silently as a
*baseline* (no alerts) so you aren't spammed with the whole backlog. After that,
each genuinely-new job is (optionally) AI-tailored and emailed: answered screening
questions, a ready cover letter, and a tailored resume PDF attached.

If no profile is configured, it falls back to the pre-AI alert (raw description +
detected screening hints).
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass

from applyfirst import log
from applyfirst.detector import detect_and_store
from applyfirst.notify.compose import build_job_email, build_tailored_email
from applyfirst.pdf import render_resume_pdf
from applyfirst.screening import detect_screening_hints

_NONALNUM = re.compile(r"[^A-Za-z0-9]+")
_LOG = log.get_logger("pipeline")


@dataclass(slots=True)
class CycleResult:
    new_total: int = 0
    emailed: int = 0
    email_errors: int = 0
    baselined: int = 0


def _safe_filename(name: str) -> str:
    base = _NONALNUM.sub("_", (name or "resume").strip()).strip("_") or "resume"
    return f"{base}_resume.pdf"


def run_cycle(store, source, notifier=None, engine=None, profile=None,
              fetch_details: bool = True, verbose: bool = True,
              keyword_pause: tuple[float, float] = (1.0, 2.5)) -> CycleResult:
    result = CycleResult()
    keywords = store.active_keywords()

    for i, keyword in enumerate(keywords):
        raw = source.search_latest(keyword)

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
            subject, text, html, attachments = _compose_for(row, engine, profile, verbose)
            if notifier is not None:
                try:
                    notifier.send(subject, text, html, attachments)
                    result.emailed += 1
                except Exception as exc:
                    result.email_errors += 1
                    print(f"     ! email failed: {exc}")
                    log.event(_LOG, "email_failed", level=logging.ERROR,
                              title=row["title"], error=str(exc))

        _pause(i, keywords, keyword_pause)

    # Heartbeat for the `health` command — never let it break a cycle.
    try:
        store.touch_heartbeat()
    except Exception:
        pass
    log.event(_LOG, "cycle_complete", new=result.new_total, emailed=result.emailed,
              email_errors=result.email_errors, baselined=result.baselined)
    return result


def _compose_for(row, engine, profile, verbose):
    description = row["raw_description"] or ""

    if engine is not None and profile is not None:
        res = engine.build(description, profile)
        attachments = None
        pdf_name = None
        try:
            pdf_bytes = render_resume_pdf(profile, res.package.resume_overrides)
            pdf_name = _safe_filename(profile.full_name)
            attachments = [(pdf_name, pdf_bytes, "application/pdf")]
        except Exception as exc:
            print(f"     ! PDF render failed: {exc}")
            log.event(_LOG, "pdf_render_failed", level=logging.WARNING,
                      title=row["title"], error=str(exc))
        if verbose:
            print(f"   + {row['posted_at'] or '?'} UTC  {row['title']}")
            print(f"     {row['url']}")
            print(f"     AI: {res.provider} · {len(res.package.screening_questions)} answer(s)"
                  + (" · resume.pdf" if attachments else ""))
        subject, text, html = build_tailored_email(
            row, res.package, res.ai_available, pdf_name, pdf_failed=attachments is None)
        return subject, text, html, attachments

    # No profile configured → pre-AI alert.
    hints = detect_screening_hints(description)
    if verbose:
        print(f"   + {row['posted_at'] or '?'} UTC  {row['title']}")
        print(f"     {row['url']}")
        if hints:
            print(f"     📋 {len(hints)} instruction line(s) detected")
    subject, text, html = build_job_email(row, hints)
    return subject, text, html, None


def _pause(i: int, keywords: list[str], bounds: tuple[float, float]) -> None:
    if i < len(keywords) - 1:
        time.sleep(random.uniform(*bounds))
