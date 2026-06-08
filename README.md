# ApplyFirst

Personal, always-on job-catcher for **onlinejobs.ph**. It watches your saved keyword
searches and, the moment a genuinely-new job appears, builds a complete application
package — employer digest, **auto-answered screening questions**, a ready-to-paste
cover letter, and a **tailored resume PDF** — then emails you a private link so you
can apply first.

> **Status:** V1 in design/build (personal use, onlinejobs.ph only).
> Full design spec: [`docs/superpowers/specs/2026-06-08-applyfirst-v1-design.md`](docs/superpowers/specs/2026-06-08-applyfirst-v1-design.md)

## The one loop (SLC)

Every ~5 min → run your keyword searches on onlinejobs.ph (logged in) → detect new
jobs → build the application package → email a private link → **apply first**.

## Why it wins

Employers bury **screening questions** in posts ("start your reply with the word…",
"answer these 3 things…") to filter out mass-appliers. ApplyFirst detects them and
drafts truthful answers in your voice — so you visibly read the post. That, plus
speed, is the edge.

## Stack

| Piece | Choice |
|---|---|
| Language | Python |
| Web UI | FastAPI + Jinja |
| Scraping | Playwright (logged-in, per-keyword, newest-first) |
| Storage | SQLite (→ Postgres in V2) |
| AI | Free LLM (Gemini) behind a swappable provider + rules fallback |
| PDF | WeasyPrint |
| Email | Resend |
| Runtime | Single always-on VPS (Docker), ~$6/mo |

## Roadmap

- **V1** (this repo) — personal, onlinejobs.ph only.
- **V2** — public + paid: multi-user, auth, billing, more job sites (Upwork first).

## Setup

_Build in progress — setup instructions land as milestones complete. See the build
milestones at the end of the design spec._
