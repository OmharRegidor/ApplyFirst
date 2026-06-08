"""ApplyFirst CLI.

    # one cycle (preview emails in console unless email is configured)
    python -m applyfirst.cli poll -k "virtual assistant" -k "customer service"

    # run forever: poll every ~5 min and email new jobs
    python -m applyfirst.cli run

    # see what's been caught
    python -m applyfirst.cli list

Email is configured via .env (see .env.example). Without it, alerts print to the
console so you can still see exactly what would be sent.
"""

from __future__ import annotations

import argparse
import random
import sys
import time

from applyfirst.config import Settings, load_settings
from applyfirst.models import RawJob
from applyfirst.notify import ConsoleNotifier, SmtpNotifier
from applyfirst.pipeline import run_cycle
from applyfirst.profile import load_profile
from applyfirst.sources.onlinejobsph import OnlineJobsPHSource
from applyfirst.store import Store
from applyfirst.tailor import GeminiProvider, TailoringEngine


def _build_notifier(s: Settings, force_console: bool):
    if force_console or not s.email_enabled or not (s.smtp_user and s.smtp_password):
        return ConsoleNotifier()
    return SmtpNotifier(
        s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password,
        sender=s.alert_from or s.smtp_user,
        recipient=s.alert_to or s.smtp_user,
    )


def _seed_keywords(store: Store, cli_keywords, settings: Settings) -> None:
    for kw in (cli_keywords or []):
        store.add_search(kw)
    for kw in settings.keywords:
        store.add_search(kw)


def cmd_poll(args: argparse.Namespace) -> int:
    s = load_settings()
    store = Store(args.db or s.db)
    try:
        _seed_keywords(store, args.keyword, s)
        if not store.active_keywords():
            print('No saved searches. Add one, e.g.  poll -k "virtual assistant"')
            return 1
        notifier = None if args.no_email else _build_notifier(s, args.preview)
        source = OnlineJobsPHSource()
        try:
            res = run_cycle(store, source, notifier=notifier, fetch_details=not args.no_detail)
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
    interval = args.interval or s.poll_interval
    store = Store(args.db or s.db)
    _seed_keywords(store, args.keyword, s)
    keywords = store.active_keywords()
    if not keywords:
        print('No saved searches. Add one, e.g.  run -k "virtual assistant"')
        store.close()
        return 1

    notifier = _build_notifier(s, args.preview)
    print("ApplyFirst — continuous mode")
    print(f"  keywords : {', '.join(keywords)}")
    print(f"  interval : every ~{interval}s")
    print(f"  alerts   : {notifier.describe()}")
    print("  (Ctrl+C to stop)\n")

    source = OnlineJobsPHSource()
    cycle = 0
    try:
        while True:
            cycle += 1
            print(f"--- cycle {cycle} ---")
            try:
                res = run_cycle(store, source, notifier=notifier)
                summary = f"  new={res.new_total} emailed={res.emailed}"
                if res.email_errors:
                    summary += f" email_errors={res.email_errors}"
                if res.baselined:
                    summary += f" baselined={res.baselined}"
                print(summary)
            except Exception as exc:
                print(f"  ! cycle error: {exc}")
            nap = interval + random.uniform(0, min(30.0, interval * 0.1))
            print(f"  next poll in ~{int(nap)}s\n")
            time.sleep(nap)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        source.close()
        store.close()
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
    p_poll.add_argument("--no-email", action="store_true", help="don't send or preview email")
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

    p_list = sub.add_parser("list", help="list recently caught jobs")
    p_list.add_argument("--limit", type=int, default=30)
    p_list.set_defaults(func=cmd_list)

    p_tailor = sub.add_parser("tailor", help="AI-tailor an application for a job (preview)")
    p_tailor.add_argument("url", nargs="?", help="job URL (default: most recent caught job)")
    p_tailor.set_defaults(func=cmd_tailor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
