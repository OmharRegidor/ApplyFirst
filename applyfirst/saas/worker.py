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
- ``invalid_grant`` / insufficient scope → clear the user's gmail credential (stop retrying),
  then tell the user by email so they can reconnect (B6, ``reconnect.py``).

Run it:
    python -m applyfirst.saas.worker --once        # one deterministic cycle (also what tests call)
    python -m applyfirst.saas.worker               # long-running daemon (loops with jitter)
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from applyfirst import log
from applyfirst.notify.compose import build_tailored_email
from applyfirst.saas import crypto, db, gmail_send, preview, reconnect
from applyfirst.saas.config import DEADMAN_THRESHOLD, SaaSConfig, load_saas_config
from applyfirst.tailor.contract import TailoredPackage
from applyfirst.tailor.prompt import PROMPT_FINGERPRINT

_LOG = log.get_logger("saas.worker")

_MAX_ATTEMPTS = 3                 # bounded retry on transient gmail/send failures
_DEADMAN_THRESHOLD = DEADMAN_THRESHOLD  # consecutive blind cycles before alerting the owner
_STALL_EXIT_CODE = 70             # EX_SOFTWARE: the watchdog ended a hung worker on purpose
_WATCHDOG_EVERY = 30              # seconds between watchdog checks
_OWNER_ALERT_COOLDOWN = 6 * 3600  # debounce owner alerts: at most one per 6 hours
_ALERT_RETRY = 15 * 60            # ...but an alert no channel accepted is tried again this soon
_AI_FAIL_STREAK = 2               # consecutive all-failed AI cycles before the owner is paged
_KEYWORD_PAUSE = (1.0, 2.5)      # polite gap between keyword fetches
_DETAIL_PAUSE = (0.3, 0.8)       # polite gap after a detail fetch
_MAX_DESCRIPTION = 8000          # clamp scraped job text: the daily cap limits CALLS, not
                                 # TOKENS — a pathological post must not balloon cost/DB rows
# When every watched term comes back empty, one search for this is the tie-breaker between "the
# site is down or blocking us" and "nobody's terms matched anything this cycle". onlinejobs.ph
# always has posts for it.
_CANARY_TERM = "virtual assistant"


@dataclass(slots=True)
class CycleResult:
    keywords: int = 0
    jobs_seen: int = 0
    alerts_created: int = 0
    sent: int = 0
    failed: int = 0
    capped: int = 0
    skipped: int = 0
    # None: not checked (some term returned jobs). True/False: the canary search when none did.
    site_ok: bool | None = None
    ai_calls: int = 0        # fresh tailors attempted with an AI credential configured
    ai_fallbacks: int = 0    # ...of which the AI failed and the rules fallback wrote the letter
    reconnect_mailed: int = 0  # users told by email that their Gmail connection ended (B6)


def default_engine_factory(cfg: SaaSConfig):
    """Build a tailoring engine: Gemini if a key is configured, else the rules fallback."""
    from applyfirst.tailor import GeminiProvider, TailoringEngine
    provider = (GeminiProvider(cfg.gemini_api_key, cfg.gemini_model)
                if cfg.gemini_api_key else None)
    return TailoringEngine(provider=provider)


def _invalidate_stale_cache(conn) -> int:
    """Drop every cached package once per prompt version. Returns the rows removed.

    The cache key is (job_id, profile_hash) and knows nothing about the prompt, so without
    this a retried alert could re-send a letter an older prompt wrote. The worker_meta stamp
    makes it run once per PROMPT_FINGERPRINT, not every cycle. Costs one SELECT per cycle.
    """
    if db.get_worker_meta(conn, "prompt_fingerprint") == PROMPT_FINGERPRINT:
        return 0
    # Inline on purpose: db.py (the data layer) is out of scope for this change; move this
    # next to db.purge_tailoring_cache the next time db.py opens. Left uncommitted so the
    # set_worker_meta commit below lands the delete and the stamp in one transaction.
    removed = conn.execute("DELETE FROM tailoring_cache").rowcount
    db.set_worker_meta(conn, "prompt_fingerprint", PROMPT_FINGERPRINT)
    log.event(_LOG, "tailoring_cache_invalidated", removed=removed, prompt=PROMPT_FINGERPRINT)
    return removed


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


def _tailor(conn, alert, profile, job, cfg, engine_factory, stats=None):
    """Return (package, provider, ai_available) using the cache; or None if capped.

    Only a first attempt reserves a daily-cap slot. A retry (``alert.attempts > 0``) was
    charged when it was first tailored, so a cache miss on a retry (the prompt-change wipe, or
    an edited profile) re-tailors for free: one job costs one slot, and a user already at the
    cap still gets it. Bounded by ``_MAX_ATTEMPTS``: at most ``_MAX_ATTEMPTS - 1`` free
    re-tailors per alert. A cap of 0 or less switches tailoring off for every attempt.
    """
    cached = db.cache_get(conn, alert.job_id, profile.profile_hash)
    if cached is not None:
        package = TailoredPackage.model_validate_json(cached["package_json"])
        return package, cached["provider"], cached["provider"] != "rules-fallback"

    if cfg.daily_tailor_cap <= 0:
        return None  # AI switched off (APPLYFIRST_DAILY_TAILOR_CAP=0), retries included
    if alert.attempts == 0 and not db.try_increment_ai_usage(conn, alert.user_id,
                                                             cfg.daily_tailor_cap):
        return None  # daily cap reached

    engine = engine_factory()
    result = engine.build(
        job.raw_description or "",
        preview.to_profile(full_name=profile.full_name, job_type=profile.job_type,
                           standard_subject=profile.standard_subject,
                           standard_message=profile.standard_message),
        resume_attached=False,   # the SaaS never sends a resume file (AST-guarded in tests)
    )
    db.cache_put(conn, alert.job_id, profile.profile_hash,
                 result.package.model_dump_json(), result.provider)
    if stats is not None and cfg.ai_configured:
        stats.ai_calls += 1
        stats.ai_fallbacks += 0 if result.ai_available else 1
    return result.package, result.provider, result.ai_available


def process_alert(conn, alert, cfg, master_key, *, engine_factory, sender, stats=None) -> str:
    """Tailor + send one alert. Returns the terminal-ish status it set."""
    profile = db.get_profile(conn, alert.user_id)
    if profile is None or not profile.is_activated:
        db.mark_alert(conn, alert.id, "skipped", last_error="no active profile")
        return "skipped"

    # Fetch the user's gmail token BEFORE tailoring, so we don't spend a cap slot on a
    # user who can't receive anything. Decrypted in memory only (AAD=user_id). Which grant
    # this is gets read first, so a reconnect between the two reads can only make it look older.
    connected_at = db.gmail_connected_at(conn, alert.user_id)
    refresh = db.get_gmail_refresh_token(conn, alert.user_id, master_key)
    if refresh is None:
        db.mark_alert(conn, alert.id, "skipped", last_error="gmail not connected")
        return "skipped"

    job = db.get_job(conn, alert.job_id)
    tailored = _tailor(conn, alert, profile, job, cfg, engine_factory, stats)
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
        if connected_at is None or db.gmail_connected_at(conn, alert.user_id) != connected_at:
            # The user reconnected or disconnected while this send held the old grant. That is
            # not an expiry: keep whatever they have now, and retry the alert with it.
            return _retry_later(conn, alert, "gmail changed during the send")
        # The grant is gone. Queue the email that tells the user FIRST (B6): if anything below
        # fails, the dead grant is still stored, the next alert lands here again, and nobody is
        # dropped untold. run_once sends it once the alerts are done.
        queued = reconnect.expired(conn, alert.user_id, connected_at)
        # Stop retrying this user forever; force a reconnect.
        if not reconnect.clear_dead_grant(conn, alert.user_id, connected_at):
            # A reconnect landed after the check above. Keep it. The row just queued is for the
            # old grant, so send_due drops it without a word.
            return _retry_later(conn, alert, "gmail changed during the send")
        db.mark_alert(conn, alert.id, "failed", last_error="gmail auth revoked")
        if queued:
            log.event(_LOG, "gmail_connection_ended", level=logging.WARNING,
                      user_id=alert.user_id)
            if not cfg.user_mail_configured:
                log.event(_LOG, "user_reconnect_email_skipped", level=logging.ERROR,
                          user_id=alert.user_id,
                          hint="set APPLYFIRST_SMTP_HOST, _USER and _PASSWORD so users are told")
        return "failed"
    except gmail_send.GmailSendError as exc:
        return _retry_later(conn, alert, str(exc))

    db.mark_alert(conn, alert.id, "sent", sent_at=db._now_iso())
    return "sent"


def _retry_later(conn, alert, error: str) -> str:
    """Leave the alert pending for the next cycle, or fail it once it has used every attempt."""
    db.bump_attempts(conn, alert.id)
    if alert.attempts + 1 >= _MAX_ATTEMPTS:
        db.mark_alert(conn, alert.id, "failed", last_error=error[:200])
        return "failed"
    return "pending"  # left pending → retried next cycle, never charged again (_tailor)


def run_once(conn, source, cfg, master_key, *,
             engine_factory=None, sender=None, fetch_detail: bool = True,
             polite: bool = True, beat=None) -> CycleResult:
    """Run exactly one poll→fanout→process cycle. Deterministic; what tests call.

    ``beat`` is called after every keyword polled and every alert handled, so the watchdog can
    tell a long cycle that is still moving from one that has hung.
    """
    _invalidate_stale_cache(conn)   # first: never reuse a letter an older prompt wrote
    engine_factory = engine_factory or (lambda: default_engine_factory(cfg))
    sender = sender or gmail_send.send_email
    beat = beat or (lambda: None)
    result = CycleResult()

    keywords = db.active_keywords_all(conn)
    result.keywords = len(keywords)
    for i, kw in enumerate(keywords):
        if i:
            _pause(_KEYWORD_PAUSE, polite)   # at the top, so a failed search still gets its gap
        # Every attempt is progress, a failed search included. A site that times out on each
        # term must read as blind, not as a hung worker for the watchdog to kill.
        try:
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
                beat()        # a first poll fetches ~30 detail pages; each one is progress
                if first_poll:
                    continue  # baseline: store jobs, no alerts (no backlog flood)
                for user_id in db.users_for_keyword(conn, kw):
                    before = conn.total_changes
                    db.insert_alert(conn, user_id, job_id, kw)
                    if conn.total_changes > before:
                        result.alerts_created += 1
            db.mark_keyword_polled(conn, kw, baselined=first_poll)
        finally:
            beat()

    if result.keywords and not result.jobs_seen:
        _pause(_KEYWORD_PAUSE, polite)
        result.site_ok = _site_answers(source)
        beat()

    for alert in db.pending_alerts(conn):
        try:
            status = process_alert(conn, alert, cfg, master_key,
                                   engine_factory=engine_factory, sender=sender, stats=result)
        except Exception as exc:  # backstop: never let one alert kill the cycle
            db.bump_attempts(conn, alert.id)
            db.mark_alert(conn, alert.id, "failed", last_error=str(exc)[:200])
            status = "failed"
        if status in ("sent", "failed", "capped", "skipped"):
            setattr(result, status, getattr(result, status) + 1)
        beat()

    result.reconnect_mailed = _tell_expired_users(conn, cfg, beat)

    log.event(_LOG, "cycle_complete", keywords=result.keywords, jobs=result.jobs_seen,
              alerts=result.alerts_created, sent=result.sent, failed=result.failed,
              capped=result.capped, skipped=result.skipped, ai_calls=result.ai_calls,
              ai_fallbacks=result.ai_fallbacks, reconnect_mailed=result.reconnect_mailed)
    _track_ai_failures(conn, cfg, result)
    return result


def _tell_expired_users(conn, cfg: SaaSConfig, beat) -> int:
    """B6: email every user whose Gmail connection ended and who has not been told yet, and page
    the owner when they cannot be told. Every cycle, so a mail that failed goes out on a later
    one. Returns how many were sent. Never raises: this must not cost anyone their next job."""
    try:
        out = reconnect.send_due(conn, cfg, beat=beat)
        if out.waiting:
            _alert_owner_once(
                conn, cfg, "last_reconnect_skipped_alert_at",
                "Agad cannot tell users to reconnect Gmail",
                f"{out.waiting} user(s) lost their Gmail connection and nobody told them, because no "
                "SMTP settings are set. Set APPLYFIRST_SMTP_HOST, APPLYFIRST_SMTP_USER and "
                "APPLYFIRST_SMTP_PASSWORD (fly secrets set, or the .env on the Oracle VM) and restart "
                "the worker. They are emailed on the next cycle, unless they reconnected first.",
            )
        if out.failed and out.server_down and cfg.alert_channel == "smtp":
            # Owner alerts ride the same SMTP account that could not even log in, so the alert
            # could not arrive, and trying would only add another bad login. This line is it.
            log.event(_LOG, "user_reconnect_mail_down", level=logging.CRITICAL, error=out.failed,
                      hint="owner alerts use the same SMTP account; a webhook would reach you")
        elif out.failed:
            _alert_owner_once(
                conn, cfg, "last_reconnect_failed_alert_at", "Agad's reconnect emails are failing",
                f"The mail server failed while emailing a user that their Gmail connection ended: "
                f"{out.failed}. Sending pauses for 15 minutes, then 1 hour, then 6 hours, and a "
                "worker restart ends the pause. Check the APPLYFIRST_SMTP_* settings and test them "
                "with reconnect --test (docs/OPERATIONS.md section 2 has the Fly and Oracle "
                "commands).",
            )
        if out.rejected and not out.failed:
            # Not when the round paused: then the refusals were the server's, and the alert above
            # already says so. This one would claim the opposite.
            _alert_owner_once(
                conn, cfg, "last_reconnect_rejected_alert_at",
                "Agad's reconnect email to a user was refused",
                f"The mail server refused the reconnect email to {out.rejected} user(s): "
                f"{out.rejected_error}. The login works, so this is about that message, not the "
                "settings. Agad retries it, less often as time goes on, and gives up on a user "
                "after 3 days of refusals if other emails go through meanwhile.",
            )
        if out.gave_up:
            _alert_owner_once(
                conn, cfg, "last_reconnect_gaveup_alert_at",
                "Agad gave up telling a user to reconnect Gmail",
                f"After 3 days of refusals, Agad stopped trying to email {out.gave_up} user(s) "
                "that their Gmail connection ended, so they have not been told. Their user ids are "
                "in the user_reconnect_email_refused log lines with gave_up true.",
            )
        return out.sent
    except Exception as exc:  # noqa: BLE001 — the letters matter more than this notice
        log.event(_LOG, "user_reconnect_round_failed", level=logging.ERROR, error=str(exc)[:200])
        return 0


def _track_ai_failures(conn, cfg: SaaSConfig, result: CycleResult) -> None:
    """A credential is set, yet every letter was the user's own message: a wrong, revoked or
    unbilled key looks exactly like "AI on" from the outside. One such cycle can be a passing
    Gemini overload, so the owner is paged only after ``_AI_FAIL_STREAK`` in a row. A cycle with
    no AI calls leaves the streak alone, so a quiet deploy still gets there."""
    if not result.ai_calls:
        return
    if result.ai_fallbacks < result.ai_calls:
        db.set_worker_meta(conn, "ai_failed_cycles", "0")
        return
    streak = int(db.get_worker_meta(conn, "ai_failed_cycles") or "0") + 1
    db.set_worker_meta(conn, "ai_failed_cycles", str(streak))
    log.event(_LOG, "ai_all_failed", level=logging.ERROR, calls=result.ai_calls, streak=streak,
              hint="every AI call fell back; see ai_call_failed for the status code")
    if streak >= _AI_FAIL_STREAK:
        _alert_owner_once(
            conn, cfg, "last_ai_failed_alert_at", "Agad's AI calls are failing",
            f"Every AI call failed for {streak} cycles in a row, so those letters went out as the "
            "user's own message. The ai_call_failed log events carry each status code: 400 or 403 "
            "usually means the Gemini credential or billing, 429 or 5xx a Gemini outage.",
        )


def _site_answers(source) -> bool:
    """One search for a term that always has posts. True if onlinejobs.ph answered with jobs."""
    try:
        return len(source.search_latest(_CANARY_TERM)) > 0
    except Exception as exc:  # noqa: BLE001 — a failure here is the answer
        log.event(_LOG, "site_check_failed", level=logging.WARNING, error=str(exc)[:200])
        return False


def _record_heartbeat(conn, result: CycleResult, cfg: SaaSConfig | None = None) -> None:
    """Heartbeat + dead-man's switch — alerts the OWNER (never tenants).

    ``cfg`` is optional so unit tests can exercise the detection/log path alone; when it is
    provided and the switch trips, a debounced owner alert is dispatched via ``notify``.
    """
    db.set_worker_meta(conn, "last_cycle_at", db._now_iso())
    # Zero jobs across every watched term is blind only if the canary search failed too. One
    # user watching a term that simply has no posts must not page anyone.
    blind = result.keywords > 0 and result.jobs_seen == 0 and not result.site_ok
    count = int(db.get_worker_meta(conn, "blind_cycles") or "0")
    count = count + 1 if blind else 0
    db.set_worker_meta(conn, "blind_cycles", str(count))
    if count >= _DEADMAN_THRESHOLD:
        log.event(_LOG, "worker_blind", level=logging.CRITICAL, consecutive=count,
                  hint="onlinejobs.ph returned 0 jobs for several cycles — check for an IP block")
        if cfg is not None:
            _maybe_alert_owner(conn, cfg, count)


def _alert_owner_once(conn, cfg: SaaSConfig, meta_key: str, subject: str, body: str) -> bool:
    """Send an owner alert at most once per ``_OWNER_ALERT_COOLDOWN`` for this ``meta_key``.

    Each kind of problem keeps its own stamp, so a blind worker cannot silence a failing backup.
    The full cooldown starts only once a channel accepted the alert (or none is set up, when
    retrying would only repeat the same log line). An alert that failed on a configured channel
    is tried again after ``_ALERT_RETRY``. Returns True when it was sent, False otherwise.
    """
    last = db.get_worker_meta(conn, meta_key)
    now = time.time()
    if last is not None and (now - float(last)) < _OWNER_ALERT_COOLDOWN:
        return False
    from applyfirst.saas import notify
    delivered = notify.send_owner_alert(cfg, subject, body)
    stamp = now if delivered or cfg.alert_channel is None else now - _OWNER_ALERT_COOLDOWN + _ALERT_RETRY
    db.set_worker_meta(conn, meta_key, str(stamp))
    return delivered


def _maybe_alert_owner(conn, cfg: SaaSConfig, count: int) -> None:
    """Send the owner a 'worker blind' alert, at most once per ``_OWNER_ALERT_COOLDOWN``."""
    _alert_owner_once(
        conn, cfg, "last_owner_alert_at", "Agad worker is blind",
        f"onlinejobs.ph returned 0 jobs for {count} consecutive poll cycles. This is likely "
        "an IP block or a layout change. Check the worker logs (fly logs, or "
        "journalctl -u applyfirst-saas-worker).",
    )


def _startup_checks(conn, cfg: SaaSConfig) -> None:
    """Say, loudly and once, when a production deploy is missing something it cannot run well
    without. A development box (secure cookies off) is left alone."""
    log.event(_LOG, "worker_started", ai=cfg.ai_configured, alerts=cfg.alert_channel or "none",
              interval=cfg.worker_interval, backup_in_worker=cfg.backup_in_worker,
              stall_seconds=cfg.worker_stall_seconds)
    # /health reads this rather than the web process's own settings: the worker is what writes
    # the letters, and on Oracle the two restart separately.
    db.set_worker_meta(conn, "ai_state", "on" if cfg.ai_configured
                       else "off_ok" if cfg.ai_off_ok else "off")
    reconnect.reset_backoff(conn)   # a restart usually follows a settings fix, so try mail at once
    if not cfg.is_production:
        return
    if cfg.alert_channel is None:
        log.event(_LOG, "owner_alerts_not_configured", level=logging.CRITICAL,
                  hint="set APPLYFIRST_ALERT_WEBHOOK, or the SMTP settings and APPLYFIRST_OWNER_EMAIL")
    if not cfg.user_mail_configured:
        log.event(_LOG, "user_mail_not_configured", level=logging.ERROR,
                  hint="set APPLYFIRST_SMTP_HOST, _USER and _PASSWORD, or nobody is told when "
                       "Google ends their Gmail connection")
    if not cfg.ai_configured and cfg.ai_off_ok:
        log.event(_LOG, "ai_off_by_choice", level=logging.WARNING,
                  hint="APPLYFIRST_AI_OFF_OK is set; letters are the user's own message")
    elif not cfg.ai_configured:
        log.event(_LOG, "ai_not_configured", level=logging.CRITICAL,
                  hint="set GEMINI_API_KEY; until then every letter is the user's own message")
        _alert_owner_once(
            conn, cfg, "last_ai_alert_at", "Agad is sending letters without AI",
            "The worker started with no Gemini credential, so every application is the user's "
            "own standard message with blank answers and an 'AI unavailable' line. Set "
            "GEMINI_API_KEY (fly secrets set, or the .env on the Oracle VM) and restart the "
            "worker (on Oracle, restart applyfirst-saas-web too). If the AI is off on purpose, "
            "set APPLYFIRST_AI_OFF_OK=1 instead.",
        )


def _maybe_backup(conn, cfg: SaaSConfig, *, today: str | None = None) -> bool:
    """Take today's backup if this host asked the worker to and it has not been taken yet.

    Stamped only on success, so a failed backup is retried after the next cycle. Returns True
    when a backup was written.
    """
    if not cfg.backup_in_worker:
        return False
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if db.get_worker_meta(conn, "last_backup_date") == today:
        return False
    from applyfirst.saas import backup
    try:
        backup.run_backup(cfg)
    except Exception as exc:  # noqa: BLE001 — a failed backup must never stop the polling
        log.event(_LOG, "backup_failed", level=logging.ERROR, error=str(exc)[:200])
        _alert_owner_once(
            conn, cfg, "last_backup_alert_at", "Agad backup failed",
            f"The daily database backup failed: {str(exc)[:200]}. The worker retries after each "
            "cycle. A full disk is the usual cause.",
        )
        return False
    db.set_worker_meta(conn, "last_backup_date", today)
    return True


class _Watchdog:
    """Ends a hung worker so its supervisor can start a fresh one.

    Armed only while a cycle runs, so the long sleep between cycles never counts. Inside a
    cycle, ``run_once`` beats after every keyword and every alert, so a cycle that is long but
    still moving is left alone. If ``limit`` seconds pass with no beat, the process exits with
    ``_STALL_EXIT_CODE``. ``os._exit`` on purpose: a thread cannot raise into a main thread that
    is stuck in a socket read, and a hung process is exactly the case this is for. SQLite is
    crash-safe, so nothing half-written survives.
    """

    def __init__(self, limit: float, *, clock=time.monotonic, exit_fn=os._exit):
        self.limit = limit
        self._clock, self._exit = clock, exit_fn
        self._last = clock()
        self._armed = False

    def beat(self) -> None:
        self._last = self._clock()

    def arm(self) -> None:
        self._last = self._clock()
        self._armed = True

    def disarm(self) -> None:
        self._armed = False

    def check(self) -> bool:
        """Exit if a cycle has gone ``limit`` seconds without progress. True if it fired."""
        if not self._armed:
            return False
        idle = self._clock() - self._last
        if idle <= self.limit:
            return False
        log.event(_LOG, "worker_stalled", level=logging.CRITICAL, idle_seconds=int(idle),
                  limit=int(self.limit), hint="exiting so the supervisor starts a fresh worker")
        self._exit(_STALL_EXIT_CODE)
        return True

    def start(self, every: float = _WATCHDOG_EVERY) -> threading.Thread:
        stop = threading.Event()

        def loop():
            while not stop.wait(every):
                self.check()

        t = threading.Thread(target=loop, name="worker-watchdog", daemon=True)
        t.start()
        return t


def _cycle(conn, source, cfg, master_key, dog: _Watchdog | None = None) -> None:
    """One full turn: poll, heartbeat, purge, and the day's backup, watched if ``dog`` is set."""
    if dog is not None:
        dog.arm()
    try:
        result = run_once(conn, source, cfg, master_key, beat=dog.beat if dog else None)
        _record_heartbeat(conn, result, cfg)
        db.purge_tailoring_cache(conn)
        _maybe_backup(conn, cfg)
    finally:
        if dog is not None:
            dog.disarm()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="applyfirst.saas.worker")
    parser.add_argument("--once", action="store_true",
                        help="run a single cycle and exit (default: loop forever)")
    parser.add_argument("--interval", type=int, default=None,
                        help="seconds between cycles (default: config worker_interval)")
    args = parser.parse_args(argv)

    cfg = load_saas_config()
    log.configure(cfg.log_json, cfg.log_level)   # first, or every event below is dropped
    try:
        master_key = crypto.load_master_key()
    except crypto.CryptoError as exc:
        log.event(_LOG, "worker_no_master_key", level=logging.CRITICAL, error=str(exc))
        # It never reaches a first cycle, so /health would only notice much later. Say so now.
        # The message names settings and paths, never key material.
        try:
            conn = db.init_db(cfg.db_path)
            _alert_owner_once(conn, cfg, "last_start_alert_at", "Agad worker cannot start",
                              f"The worker cannot load its master key: {str(exc)[:200]}. "
                              "Nobody receives anything until this is fixed.")
            conn.close()
        except Exception as alert_exc:  # noqa: BLE001 — still exit 1 whatever happens here
            log.event(_LOG, "worker_start_alert_failed", level=logging.ERROR,
                      error=str(alert_exc)[:200])
        return 1

    from applyfirst.sources.base import make_client
    from applyfirst.sources.onlinejobsph import OnlineJobsPHSource

    conn = db.init_db(cfg.db_path)
    source = OnlineJobsPHSource(make_client())
    interval = args.interval if args.interval is not None else cfg.worker_interval
    _startup_checks(conn, cfg)

    if args.once:
        _cycle(conn, source, cfg, master_key)
        return 0

    dog = _Watchdog(cfg.worker_stall_seconds)
    dog.start()
    while True:
        try:
            _cycle(conn, source, cfg, master_key, dog)
        except Exception as exc:
            log.event(_LOG, "worker_cycle_crashed", level=logging.ERROR, error=str(exc)[:200])
        # Two-sided jitter (±worker_jitter fraction) so the cadence centers on `interval`.
        delay = interval + random.uniform(-1.0, 1.0) * interval * cfg.worker_jitter
        time.sleep(max(1.0, delay))


if __name__ == "__main__":
    raise SystemExit(main())
