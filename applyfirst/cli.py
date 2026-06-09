"""ApplyFirst CLI.

    # one cycle (previews emails in console unless email is configured)
    python -m applyfirst.cli poll -k "virtual assistant" -k "customer service"

    # run forever: poll every ~5 min and email new (AI-tailored) jobs
    python -m applyfirst.cli run

    # preview a full AI package for one job (most recent caught job, or a URL)
    python -m applyfirst.cli tailor [URL]

    # see what's been caught
    python -m applyfirst.cli list

    # is the run loop alive? (exit 1 if stale — for cron/uptime watchdogs)
    python -m applyfirst.cli health

    # write a gzipped SQLite backup (run also auto-backs-up once/day)
    python -m applyfirst.cli backup

Email + AI are configured via .env (see .env.example) and profile.yaml. Without
email, alerts print to the console. Without a profile, alerts are the pre-AI form.
Set APPLYFIRST_LOG_JSON=1 for structured JSON event logs on stderr.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from applyfirst import backup as backup_mod
from applyfirst import log
from applyfirst.config import Settings, load_settings
from applyfirst.health import health_status, parse_iso
from applyfirst.models import RawJob
from applyfirst.notify import ConsoleNotifier, SmtpNotifier
from applyfirst.pdf import render_resume_pdf
from applyfirst.pipeline import run_cycle
from applyfirst.profile import load_profile
from applyfirst.sources.onlinejobsph import OnlineJobsPHSource
from applyfirst.store import Store
from applyfirst.tailor import GeminiProvider, TailoringEngine

_LOG = log.get_logger("cli")


def _build_notifier(s: Settings, force_console: bool):
    if force_console or not s.email_enabled or not (s.smtp_user and s.smtp_password):
        return ConsoleNotifier()
    return SmtpNotifier(
        s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password,
        sender=s.alert_from or s.smtp_user, recipient=s.alert_to or s.smtp_user,
    )


def _build_engine_profile(s: Settings):
    """Return (engine, profile) if a profile.yaml exists, else (None, None)."""
    try:
        profile = load_profile(s.profile_path)
    except FileNotFoundError:
        return None, None
    provider = GeminiProvider(s.gemini_api_key, s.gemini_model) if s.gemini_api_key else None
    return TailoringEngine(provider=provider), profile


def _seed_keywords(store: Store, cli_keywords, settings: Settings) -> None:
    for kw in (cli_keywords or []):
        store.add_search(kw)
    for kw in settings.keywords:
        store.add_search(kw)


def _ai_status(engine, profile, s: Settings) -> str:
    if profile is None:
        return "off (no profile.yaml — sending pre-AI alerts)"
    return "Gemini" if s.gemini_api_key else "rules-fallback (no GEMINI_API_KEY)"


def _maybe_daily_backup(store: Store, db_path: str) -> None:
    """Back up the DB once per UTC day during a `run` loop. Never fatal."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if store.get_meta("last_backup_date") == today:
        return
    try:
        path = backup_mod.backup_db(db_path)
        store.set_meta("last_backup_date", today)
        print(f"  💾 backup: {path}")
        log.event(_LOG, "backup_created", path=str(path))
    except Exception as exc:
        print(f"  ! backup failed: {exc}")
        log.event(_LOG, "backup_failed", level=logging.ERROR, error=str(exc))


def cmd_poll(args: argparse.Namespace) -> int:
    s = load_settings()
    log.configure(s.log_json, s.log_level)
    store = Store(args.db or s.db)
    try:
        _seed_keywords(store, args.keyword, s)
        if not store.active_keywords():
            print('No saved searches. Add one, e.g.  poll -k "virtual assistant"')
            return 1
        if args.no_email:
            notifier, engine, profile = None, None, None
        else:
            notifier = _build_notifier(s, args.preview)
            engine, profile = _build_engine_profile(s)
            print(f"AI tailoring: {_ai_status(engine, profile, s)}")
        source = OnlineJobsPHSource()
        try:
            res = run_cycle(store, source, notifier=notifier, engine=engine, profile=profile,
                            fetch_details=not args.no_detail)
        finally:
            source.close()
        tail = "" if notifier is None else f", emailed={res.emailed}"
        if res.baselined:
            print(f"\nBaseline stored: {res.baselined} jobs (no alerts on first run).")
        print(f"Total new this cycle: {res.new_total}{tail}  (db holds {store.count_jobs()} jobs)")
        return 0
    finally:
        store.close()


def cmd_run(args: argparse.Namespace) -> int:
    s = load_settings()
    log.configure(s.log_json, s.log_level)
    interval = args.interval or s.poll_interval
    db_path = args.db or s.db
    store = Store(db_path)
    _seed_keywords(store, args.keyword, s)
    keywords = store.active_keywords()
    if not keywords:
        print('No saved searches. Add one, e.g.  run -k "virtual assistant"')
        store.close()
        return 1

    notifier = _build_notifier(s, args.preview)
    engine, profile = _build_engine_profile(s)
    print("ApplyFirst — continuous mode")
    print(f"  keywords : {', '.join(keywords)}")
    print(f"  interval : every ~{interval}s")
    print(f"  alerts   : {notifier.describe()}")
    print(f"  AI       : {_ai_status(engine, profile, s)}")
    print("  (Ctrl+C to stop)\n")
    log.event(_LOG, "run_started", keywords=keywords, interval=interval)

    source = OnlineJobsPHSource()
    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"--- cycle {cycle} ---")
            try:
                _maybe_daily_backup(store, db_path)
                res = run_cycle(store, source, notifier=notifier, engine=engine, profile=profile)
                summary = f"  new={res.new_total} emailed={res.emailed}"
                if res.email_errors:
                    summary += f" email_errors={res.email_errors}"
                if res.baselined:
                    summary += f" baselined={res.baselined}"
                print(summary)
            except Exception as exc:
                print(f"  ! cycle error: {exc}")
                log.event(_LOG, "cycle_error", level=logging.ERROR, cycle=cycle, error=str(exc))
            nap = interval + random.uniform(0, min(30.0, interval * 0.1))
            print(f"  next poll in ~{int(nap)}s\n")
            time.sleep(nap)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        source.close()
        store.close()
    return 0


def _print_package(title: str, res) -> None:
    pkg = res.package
    print("=" * 70)
    print("TITLE:", title)
    print(f"AI: {res.provider}  (ai_available={res.ai_available})")
    print("=" * 70)
    print("\n## DIGEST\n" + (pkg.digest or "—"))
    if pkg.compliance_token:
        print(f"\n## ⚠ START YOUR REPLY WITH:\n{pkg.compliance_token}")
    print("\n## SCREENING QUESTIONS & DRAFTED ANSWERS")
    if pkg.screening_questions:
        for i, qa in enumerate(pkg.screening_questions, 1):
            print(f"  {i}. Q: {qa.question}")
            print(f"     A: {qa.drafted_answer or '(answer manually — AI unavailable)'}")
    else:
        print("  (none detected)")
    print("\n## COVER LETTER\n" + (pkg.cover_letter or "—"))
    ro = pkg.resume_overrides
    print("\n## RESUME TWEAKS")
    print("  summary:", ro.summary or "—")
    print("  emphasize:", ", ".join(ro.emphasize_skills) or "—")
    for tb in ro.tailored_bullets:
        print(f"  [{tb.role_id}]")
        for b in tb.bullets:
            print(f"    - {b}")


def cmd_tailor(args: argparse.Namespace) -> int:
    s = load_settings()
    try:
        profile = load_profile(s.profile_path)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    source = OnlineJobsPHSource()
    try:
        if args.url:
            ext_id = args.url.rstrip("/").split("-")[-1]
            raw = RawJob(source="onlinejobs.ph", external_id=ext_id, url=args.url, title="(from url)")
            title = args.url
            description = source.fetch_detail(raw).description
        else:
            store = Store(args.db or s.db)
            rows = store.recent_jobs(1)
            store.close()
            if not rows:
                print("No caught jobs yet and no URL given. Run a poll first, or pass a job URL.")
                return 1
            row = rows[0]
            title = row["title"]
            description = row["raw_description"]
            if not description:
                raw = RawJob(source=row["source"], external_id=row["external_id"],
                             url=row["url"], title=row["title"])
                description = source.fetch_detail(raw).description
    finally:
        source.close()

    provider = GeminiProvider(s.gemini_api_key, s.gemini_model) if s.gemini_api_key else None
    if provider is None:
        print("(No GEMINI_API_KEY set — using the rules fallback. Add a key in .env for AI answers.)\n")
    res = TailoringEngine(provider=provider).build(description, profile)
    _print_package(title, res)

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    pdf_path = out_dir / "tailored_resume.pdf"
    pdf_path.write_bytes(render_resume_pdf(profile, res.package.resume_overrides))
    print(f"\n📎 Tailored resume PDF written to: {pdf_path.resolve()}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    s = load_settings()
    store = Store(args.db or s.db)
    try:
        rows = store.recent_jobs(args.limit)
        if not rows:
            print('No jobs yet. Run: poll -k "virtual assistant"')
            return 0
        for r in rows:
            print(f"[{r['status']}] {r['posted_at'] or '?'}  {r['title']}")
            print(f"        {r['url']}")
        return 0
    finally:
        store.close()


def cmd_health(args: argparse.Namespace) -> int:
    """Report whether the `run` loop is fresh; exit 1 when stale (for watchdogs)."""
    s = load_settings()
    store = Store(args.db or s.db)
    try:
        last_iso = store.get_meta("last_cycle_at")
    finally:
        store.close()
    max_stale = args.max_stale if args.max_stale is not None else max(2 * s.poll_interval, 600)
    st = health_status(parse_iso(last_iso), datetime.now(timezone.utc), max_stale)
    suffix = f"  (last_cycle_at={last_iso} UTC)" if last_iso else ""
    print(st["message"] + suffix)
    return 0 if st["ok"] else 1


def cmd_backup(args: argparse.Namespace) -> int:
    s = load_settings()
    try:
        path = backup_mod.backup_db(args.db or s.db, backup_dir=args.dir, keep=args.keep)
    except Exception as exc:  # unwritable dir, locked/corrupt DB, etc. — clean error, not a traceback
        print(f"Backup failed: {exc}")
        return 1
    print(f"Backup written: {path.resolve()}  ({path.stat().st_size} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # avoid mojibake on Windows consoles
    except Exception:
        pass

    parser = argparse.ArgumentParser(prog="applyfirst", description="ApplyFirst job-catcher")
    parser.add_argument("--db", default=None, help="SQLite path (default: .env or applyfirst.db)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_poll = sub.add_parser("poll", help="run one poll cycle")
    p_poll.add_argument("--keyword", "-k", action="append",
                        help="keyword to search (repeatable; saved for future runs)")
    p_poll.add_argument("--no-detail", action="store_true", help="skip fetching full descriptions")
    p_poll.add_argument("--no-email", action="store_true", help="don't send or preview (and skip AI)")
    p_poll.add_argument("--preview", action="store_true",
                        help="print emails to console instead of sending")
    p_poll.set_defaults(func=cmd_poll)

    p_run = sub.add_parser("run", help="poll continuously and email new jobs")
    p_run.add_argument("--keyword", "-k", action="append",
                       help="keyword to search (repeatable; saved)")
    p_run.add_argument("--interval", type=int, default=None, help="seconds between polls")
    p_run.add_argument("--preview", action="store_true",
                       help="print emails to console instead of sending")
    p_run.set_defaults(func=cmd_run)

    p_tailor = sub.add_parser("tailor", help="AI-tailor an application for a job (preview + PDF)")
    p_tailor.add_argument("url", nargs="?", help="job URL (default: most recent caught job)")
    p_tailor.set_defaults(func=cmd_tailor)

    p_list = sub.add_parser("list", help="list recently caught jobs")
    p_list.add_argument("--limit", type=int, default=30)
    p_list.set_defaults(func=cmd_list)

    p_health = sub.add_parser("health", help="check the run loop's heartbeat (exit 1 if stale)")
    p_health.add_argument("--max-stale", type=int, default=None,
                          help="max seconds since last cycle before STALE (default: 2×interval, min 600)")
    p_health.set_defaults(func=cmd_health)

    p_backup = sub.add_parser("backup", help="write a gzipped SQLite backup")
    p_backup.add_argument("--dir", default="backups", help="backup directory (default: backups)")
    p_backup.add_argument("--keep", type=int, default=7, help="how many backups to retain (default: 7)")
    p_backup.set_defaults(func=cmd_backup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
