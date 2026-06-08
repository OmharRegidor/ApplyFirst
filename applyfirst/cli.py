"""Milestone-1 CLI: run a poll cycle and inspect caught jobs.

    python -m applyfirst.cli poll -k "virtual assistant" -k "customer service"
    python -m applyfirst.cli list

No AI, no web, no email yet — this proves the catch loop works end to end.
"""

from __future__ import annotations

import argparse
import random
import sys
import time

from applyfirst.detector import detect_and_store
from applyfirst.sources.onlinejobsph import OnlineJobsPHSource
from applyfirst.store import Store


def cmd_poll(args: argparse.Namespace) -> int:
    store = Store(args.db)
    try:
        for kw in args.keyword or []:
            store.add_search(kw)

        keywords = store.active_keywords()
        if not keywords:
            print('No saved searches. Add one, e.g.  poll -k "virtual assistant"')
            return 1

        source = OnlineJobsPHSource()
        total_new = 0
        try:
            for i, kw in enumerate(keywords):
                raw = source.search_latest(kw)
                res = detect_and_store(source, store, raw, fetch_details=not args.no_detail)
                total_new += len(res.new)
                print(f"[{kw}] fetched={len(raw)} new={len(res.new)} seen={res.seen}"
                      + (f" detail_errors={res.detail_errors}" if res.detail_errors else ""))
                for job in res.new:
                    ts = job.posted_at.strftime("%Y-%m-%d %H:%M") if job.posted_at else "?"
                    print(f"   + {ts} UTC  {job.title}  "
                          f"[{job.employment_type or '-'}, {job.salary_text or '-'}]")
                    print(f"     {job.url}")
                if i < len(keywords) - 1:
                    time.sleep(random.uniform(1.0, 2.5))  # polite jitter between searches
        finally:
            source.close()

        print(f"\nTotal new this cycle: {total_new}  (db now holds {store.count_jobs()} jobs)")
        return 0
    finally:
        store.close()


def cmd_list(args: argparse.Namespace) -> int:
    store = Store(args.db)
    try:
        rows = store.recent_jobs(args.limit)
        if not rows:
            print("No jobs caught yet. Run: poll -k \"virtual assistant\"")
            return 0
        for r in rows:
            print(f"[{r['status']}] {r['posted_at'] or '?'}  {r['title']}")
            print(f"        {r['url']}")
        return 0
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # avoid mojibake on Windows consoles
    except Exception:
        pass
    parser = argparse.ArgumentParser(prog="applyfirst", description="ApplyFirst job-catcher (M1)")
    parser.add_argument("--db", default="applyfirst.db", help="SQLite path (default: applyfirst.db)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_poll = sub.add_parser("poll", help="run one poll cycle")
    p_poll.add_argument("--keyword", "-k", action="append",
                        help="keyword to search (repeatable); saved for future polls")
    p_poll.add_argument("--no-detail", action="store_true",
                        help="skip fetching full descriptions (faster, fewer requests)")
    p_poll.set_defaults(func=cmd_poll)

    p_list = sub.add_parser("list", help="list recently caught jobs")
    p_list.add_argument("--limit", type=int, default=30)
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
