"""The multi-tenant polling worker (M3).

One cycle (``run_once``):
  1. POLL — for each unique keyword that an activated tenant watches, fetch onlinejobs.ph
     ONCE (politely), store new jobs in the shared ``jobs`` table (detail fetched only for
     globally-new jobs). The first poll of a keyword silently *baselines* (no alerts).
  2. FAN OUT — insert a ``user_job_alerts`` row per (activated subscriber, job).
  3. PROCESS — for each pending alert: enforce the per-user daily cap, tailor (reusing the
     ``(job_id, profile_hash)`` cache), and SEND the application via the Gmail API to the
     user's OWN inbox.

Security invariants (see docs/plans/M3-worker.md §6):
- Each ``engine.build`` sees exactly ONE user's profile + ONE public job — no cross-tenant
  context ever reaches the LLM.
- The refresh token is decrypted in memory only (AAD=user_id), never logged, never stored
  in ``last_error``.
- ``invalid_grant`` / insufficient scope → clear the user's gmail credential (stop retrying).

Run it:
    python -m applyfirst.saas.worker --once        # one deterministic cycle (also what tests call)
    python -m applyfirst.saas.worker               # long-running daemon (loops with jitter)
"""

from __future__ import annotations

import argparse
import logging
import random
import time
from dataclasses import dataclass

from applyfirst import log
from applyfirst.notify.compose import build_tailored_email
from applyfirst.saas import crypto, db, gmail_send, preview
from applyfirst.saas.config import SaaSConfig, load_saas_config
from applyfirst.tailor.contract import TailoredPackage

_LOG = log.get_logger("saas.worker")

_MAX_ATTEMPTS = 3                 # bounded retry on transient gmail/send failures
_DEADMAN_THRESHOLD = 3           # consecutive blind cycles before alerting the owner
_OWNER_ALERT_COOLDOWN = 6 * 3600  # debounce owner alerts: at most one per 6 hours
_KEYWORD_PAUSE = (1.0, 2.5)      # polite gap between keyword fetches
_DETAIL_PAUSE = (0.3, 0.8)       # polite gap after a detail fetch
_MAX_DESCRIPTION = 8000          # clamp scraped job text: the daily cap limits CALLS, not
                                 # TOKENS — a pathological post must not balloon cost/DB rows


@dataclass(slots=True)
class CycleResult:
    keywords: int = 0
    jobs_seen: int = 0
    alerts_created: int = 0
    sent: int = 0
    failed: int = 0
    capped: int = 0
    skipped: int = 0


def default_engine_factory(cfg: SaaSConfig):
    """Build a tailoring engine: Gemini if a key is configured, else the rules fallback."""
    from applyfirst.tailor import GeminiProvider, TailoringEngine
    provider = (GeminiProvider(cfg.gemini_api_key, cfg.gemini_model)
                if cfg.gemini_api_key else None)
    return TailoringEngine(provider=provider)


def _pause(bounds: tuple[float, float], polite: bool) -> None:
    if polite:
        time.sleep(random.uniform(*bounds))


def _get_or_create_job(conn, raw, source, *, fetch_detail: bool, polite: bool) -> str:
    """Return the job id for a search-result card; fetch its detail only if globally new."""
    existing = db.get_job_id(conn, raw.external_id)
    if existing is not None:
        return existing
    description = raw.preview or ""
    if fetch_detail:
        try:
            description = source.fetch_detail(raw).description
        except Exception as exc:  # a single bad detail page must not kill the cycle
            log.event(_LOG, "detail_fetch_failed", level=logging.WARNING,
                      url=raw.url, error=str(exc)[:200])
        _pause(_DETAIL_PAUSE, polite)
    posted = raw.posted_at.isoformat() if raw.posted_at else None
    return db.insert_job(
        conn, onlinejobs_id=raw.external_id, title=raw.title, url=raw.url,
        employment_type=raw.employment_type, salary_text=raw.salary_text,
        posted_at=posted, raw_description=(description or "")[:_MAX_DESCRIPTION],
    )


def _tailor(conn, alert, profile, job, cfg, engine_factory):
    """Return (package, provider, ai_available) using the cache; or None if capped."""
    cached = db.cache_get(conn, alert.job_id, profile.profile_hash)
    if cached is not None:
        package = TailoredPackage.model_validate_json(cached["package_json"])
        return package, cached["provider"], cached["provider"] != "rules-fallback"

    if not db.try_increment_ai_usage(conn, alert.user_id, cfg.daily_tailor_cap):
        return None  # daily cap reached

    engine = engine_factory()
    result = engine.build(
        job.raw_description or "",
        preview.to_profile(full_name=profile.full_name, job_type=profile.job_type,
                           standard_subject=profile.standard_subject,
                           standard_message=profile.standard_message),
    )
    db.cache_put(conn, alert.job_id, profile.profile_hash,
                 result.package.model_dump_json(), result.provider)
    return result.package, result.provider, result.ai_available


def process_alert(conn, alert, cfg, master_key, *, engine_factory, sender) -> str:
    """Tailor + send one alert. Returns the terminal-ish status it set."""
    profile = db.get_profile(conn, alert.user_id)
    if profile is None or not profile.is_activated:
        db.mark_alert(conn, alert.id, "skipped", last_error="no active profile")
        return "skipped"

    # Fetch the user's gmail token BEFORE tailoring, so we don't spend a cap slot on a
    # user who can't receive anything. Decrypted in memory only (AAD=user_id).
    refresh = db.get_gmail_refresh_token(conn, alert.user_id, master_key)
    if refresh is None:
        db.mark_alert(conn, alert.id, "skipped", last_error="gmail not connected")
        return "skipped"

    job = db.get_job(conn, alert.job_id)
    tailored = _tailor(conn, alert, profile, job, cfg, engine_factory)
    if tailored is None:
        db.mark_alert(conn, alert.id, "capped",
                      last_error=f"daily cap {cfg.daily_tailor_cap} reached")
        return "capped"
    package, _provider, ai_available = tailored

    subject, text, html = build_tailored_email(
        job.as_email_job(alert.keyword), package, ai_available)
    user = db.get_user(conn, alert.user_id)

    try:
        sender(cfg, refresh, to=user.email, subject=subject, text=text, html=html)
    except gmail_send.GmailAuthError:
        # The grant is gone — stop retrying this user forever; force a reconnect.
        db.clear_gmail_credential(conn, alert.user_id)
        db.mark_alert(conn, alert.id, "failed", last_error="gmail auth revoked")
        return "failed"
    except gmail_send.GmailSendError as exc:
        db.bump_attempts(conn, alert.id)
        if alert.attempts + 1 >= _MAX_ATTEMPTS:
            db.mark_alert(conn, alert.id, "failed", last_error=str(exc)[:200])
            return "failed"
        return "pending"  # left pending → retried next cycle (cache hit, no extra cap)

    db.mark_alert(conn, alert.id, "sent", sent_at=db._now_iso())
    return "sent"


def run_once(conn, source, cfg, master_key, *,
             engine_factory=None, sender=None, fetch_detail: bool = True,
             polite: bool = True) -> CycleResult:
    """Run exactly one poll→fanout→process cycle. Deterministic; what tests call."""
    engine_factory = engine_factory or (lambda: default_engine_factory(cfg))
    sender = sender or gmail_send.send_email
    result = CycleResult()

    keywords = db.active_keywords_all(conn)
    result.keywords = len(keywords)
    for i, kw in enumerate(keywords):
        try:
            raw_jobs = source.search_latest(kw)
        except Exception as exc:
            log.event(_LOG, "search_failed", level=logging.WARNING, keyword=kw,
                      error=str(exc)[:200])
            continue
        result.jobs_seen += len(raw_jobs)
        first_poll = not db.is_keyword_baselined(conn, kw)
        for raw in raw_jobs:
            job_id = _get_or_create_job(conn, raw, source,
                                        fetch_detail=fetch_detail, polite=polite)
            if first_poll:
                continue  # baseline: store jobs, no alerts (no backlog flood)
            for user_id in db.users_for_keyword(conn, kw):
                before = conn.total_changes
                db.insert_alert(conn, user_id, job_id, kw)
                if conn.total_changes > before:
                    result.alerts_created += 1
        db.mark_keyword_polled(conn, kw, baselined=first_poll)
        if i < len(keywords) - 1:
            _pause(_KEYWORD_PAUSE, polite)

    for alert in db.pending_alerts(conn):
        try:
            status = process_alert(conn, alert, cfg, master_key,
                                   engine_factory=engine_factory, sender=sender)
        except Exception as exc:  # backstop: never let one alert kill the cycle
            db.bump_attempts(conn, alert.id)
            db.mark_alert(conn, alert.id, "failed", last_error=str(exc)[:200])
            status = "failed"
        if status in ("sent", "failed", "capped", "skipped"):
            setattr(result, status, getattr(result, status) + 1)

    log.event(_LOG, "cycle_complete", keywords=result.keywords, jobs=result.jobs_seen,
              alerts=result.alerts_created, sent=result.sent, failed=result.failed,
              capped=result.capped, skipped=result.skipped)
    return result


def _record_heartbeat(conn, result: CycleResult, cfg: SaaSConfig | None = None) -> None:
    """Heartbeat + dead-man's switch — alerts the OWNER (never tenants).

    ``cfg`` is optional so unit tests can exercise the detection/log path alone; when it is
    provided and the switch trips, a debounced owner alert is dispatched via ``notify``.
    """
    db.set_worker_meta(conn, "last_cycle_at", db._now_iso())
    blind = result.keywords > 0 and result.jobs_seen == 0
    count = int(db.get_worker_meta(conn, "blind_cycles") or "0")
    count = count + 1 if blind else 0
    db.set_worker_meta(conn, "blind_cycles", str(count))
    if count >= _DEADMAN_THRESHOLD:
        log.event(_LOG, "worker_blind", level=logging.CRITICAL, consecutive=count,
                  hint="onlinejobs.ph returned 0 jobs for several cycles — check for an IP block")
        if cfg is not None:
            _maybe_alert_owner(conn, cfg, count)


def _maybe_alert_owner(conn, cfg: SaaSConfig, count: int) -> None:
    """Send the owner a 'worker blind' alert, at most once per ``_OWNER_ALERT_COOLDOWN``."""
    last = db.get_worker_meta(conn, "last_owner_alert_at")
    now = time.time()
    if last is not None and (now - float(last)) < _OWNER_ALERT_COOLDOWN:
        return
    from applyfirst.saas import notify
    notify.send_owner_alert(
        cfg, "ApplyFirst worker is blind",
        f"onlinejobs.ph returned 0 jobs for {count} consecutive poll cycles. This is likely "
        "an IP block or a layout change. Check the worker logs (journalctl -u applyfirst-saas-worker).",
    )
    db.set_worker_meta(conn, "last_owner_alert_at", str(now))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="applyfirst.saas.worker")
    parser.add_argument("--once", action="store_true",
                        help="run a single cycle and exit (default: loop forever)")
    parser.add_argument("--interval", type=int, default=None,
                        help="seconds between cycles (default: config worker_interval)")
    args = parser.parse_args(argv)

    cfg = load_saas_config()
    try:
        master_key = crypto.load_master_key()
    except crypto.CryptoError as exc:
        log.event(_LOG, "worker_no_master_key", level=logging.CRITICAL, error=str(exc))
        return 1

    from applyfirst.sources.base import make_client
    from applyfirst.sources.onlinejobsph import OnlineJobsPHSource

    conn = db.init_db(cfg.db_path)
    source = OnlineJobsPHSource(make_client())
    interval = args.interval if args.interval is not None else cfg.worker_interval

    if args.once:
        result = run_once(conn, source, cfg, master_key)
        _record_heartbeat(conn, result, cfg)
        db.purge_tailoring_cache(conn)
        return 0

    while True:
        try:
            result = run_once(conn, source, cfg, master_key)
            _record_heartbeat(conn, result, cfg)
            db.purge_tailoring_cache(conn)
        except Exception as exc:
            log.event(_LOG, "worker_cycle_crashed", level=logging.ERROR, error=str(exc)[:200])
        # Two-sided jitter (±worker_jitter fraction) so the cadence centers on `interval`.
        delay = interval + random.uniform(-1.0, 1.0) * interval * cfg.worker_jitter
        time.sleep(max(1.0, delay))


if __name__ == "__main__":
    raise SystemExit(main())
