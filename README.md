# ApplyFirst

Personal, always-on job-catcher for **onlinejobs.ph**. It watches your saved keyword
searches and, the moment a genuinely-new job appears, builds a complete application
package — employer digest, **auto-answered screening questions**, a ready-to-paste
cover letter, and a **tailored resume PDF** — then emails it to you (package inline,
PDF attached) so you can apply first.

> **Status:** ✅ V1 complete — a **CLI tool** (no login, no browser, $0 to run). Soak next.
> Full design spec: [`docs/superpowers/specs/2026-06-08-applyfirst-v1-design.md`](docs/superpowers/specs/2026-06-08-applyfirst-v1-design.md)

## The one loop (SLC)

Every ~5 min → run your keyword searches on onlinejobs.ph (**public HTTP, no login**) →
detect new jobs → build the application package → **email it (resume PDF attached)** →
**apply first**.

## Why it wins

Employers bury **screening questions** in posts ("start your reply with the word…",
"answer these 3 things…") to filter out mass-appliers. ApplyFirst detects them and
drafts truthful answers in your voice — so you visibly read the post. That, plus
speed, is the edge.

## Stack

| Piece | Choice |
|---|---|
| Language | Python |
| Interface | **CLI** (`python -m applyfirst.cli`) — web UI is a V2 extension |
| Scraping | **`httpx` + `selectolax`** — public reads, per-keyword, newest-first (no login, no browser) |
| Storage | SQLite (WAL) — one file (→ Postgres in V2) |
| AI | **Gemini `gemini-2.0-flash`** behind a swappable provider + **rules fallback** |
| PDF | **`fpdf2`** — pure-Python, no system deps |
| Email | **Gmail SMTP** (App Password) — package inline + resume PDF attached; console-preview fallback |
| Ops | Opt-in JSON logging · `health` heartbeat · gzipped SQLite `backup` |
| Runtime | Runs anywhere Python runs; **$0/mo** |

## Roadmap

- **V1** (this repo) — personal, onlinejobs.ph only, CLI.
- **V2** — public + paid: web UI (per-job pages, onboarding wizard), multi-user, auth,
  billing, more job sites (Upwork first). See §17 of the design spec.

## Quickstart

```bash
# one-time setup
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements-dev.txt

# run a poll cycle (keywords are saved for next time)
python -m applyfirst.cli poll -k "virtual assistant" -k "customer service"

# run again later — already-seen jobs are skipped (dedup)
python -m applyfirst.cli poll

# list recently caught jobs
python -m applyfirst.cli list

# run the tests (against saved fixtures, no network)
pytest -q
```

Flags: `--no-detail` skips fetching full descriptions (faster, fewer requests);
the global `--db PATH` (before the subcommand) chooses the SQLite file (default
`applyfirst.db`).

## Email alerts + continuous mode

Run it forever: it polls every ~5 min and **emails you the moment a new job appears**.
The **first** poll of each keyword is a silent baseline (it learns the current jobs) so
you're not flooded — only genuinely-new jobs alert.

```bash
# 1) configure email (free, one-time)
copy .env.example .env          # then edit .env  (Gmail App Password — see the file)

# 2) preview without sending (prints the alert to the console)
python -m applyfirst.cli poll -k "virtual assistant" --preview

# 3) run for real, continuously
python -m applyfirst.cli run
```

To enable real emails, set `EMAIL_ENABLED=true` and your Gmail App Password in `.env`
(steps are in `.env.example`). If email isn't configured, alerts print to the console
so nothing is lost. `.env` is git-ignored — never commit it.

## AI tailoring + resume PDF

The engine reads a job + your `profile.yaml` and drafts: answers to the buried screening
questions, the compliance token to open with, a tailored cover letter, and resume tweaks
— **truthful only** (it rephrases your real facts, never invents) — then renders a
**tailored resume PDF**. With a profile configured, `run`/`poll` email the full package
with the PDF attached; without one, they fall back to the pre-AI alert (raw description +
detected questions). No key set (or API fails) → it lists the questions for you to answer.

Every cover letter also pitches the **full range of skills in your `profile.yaml`** — not
just the role you applied for. Beyond web and app development, that includes **AI automation
with n8n** (LLM workflows wired into Gmail, Slack & Shopify, human-in-the-loop), so employers
see your breadth in the first few seconds.

```bash
# 1) free Gemini key → https://aistudio.google.com/apikey  → put GEMINI_API_KEY in .env
# 2) your resume → copy profile.example.yaml to profile.yaml and fill it in (git-ignored)

# preview a full AI package for a job (most recent caught job, or a URL).
# also writes the tailored resume to output/tailored_resume.pdf:
python -m applyfirst.cli tailor
python -m applyfirst.cli tailor "https://www.onlinejobs.ph/jobseekers/job/...-1663915"
```

## Operations (running it unattended)

For a long-lived `run`, three built-ins keep it observable and safe:

```bash
# Liveness — exit 0 if the loop is fresh, exit 1 if stale (last cycle too long ago).
# Point cron or an UptimeRobot heartbeat at this to get alerted on a silent hang.
python -m applyfirst.cli health
python -m applyfirst.cli health --max-stale 900     # custom staleness threshold (seconds)

# Backup — gzipped SQLite snapshot (online-backup API; safe while run holds the DB).
# `run` also auto-backs-up once per UTC day; keeps the last N (default 7).
python -m applyfirst.cli backup
python -m applyfirst.cli backup --dir backups --keep 14

# Structured logs — one JSON event per line on stderr (stdout stays human-readable).
# Set APPLYFIRST_LOG_JSON=1 (or in .env), then capture the stream:
APPLYFIRST_LOG_JSON=1 python -m applyfirst.cli run 2> run.jsonl
```

`backups/`, `output/`, `.env`, and `profile.yaml` are git-ignored.
