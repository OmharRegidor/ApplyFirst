# ApplyFirst — V1 Design Spec

- **Date:** 2026-06-08
- **Version:** 1.1 (Noxa team review incorporated)
- **Status:** ✅ Build-ready (P0/P1 review findings resolved)
- **Owner:** Omhar (single user for V1)
- **Working name:** ApplyFirst
- **Repo:** https://github.com/OmharRegidor/ApplyFirst

> v1.1 changelog is at the end (§19). It records the Noxa team review fixes and the move to a free host.

---

## 1. Problem & Goal

The owner manually refreshes onlinejobs.ph search pages to catch fresh job posts, racing to apply first. Two things lose jobs: (1) not seeing a post quickly enough, and (2) the time it takes to write a tailored application — especially answering the **screening questions** employers bury in posts to filter out mass-appliers.

**Goal:** A personal, always-on web app that watches the owner's onlinejobs.ph searches, and the moment a genuinely-new job appears, builds a complete, ready-to-send application package and emails a private link — so the owner can apply first, with a tailored resume and pre-answered screening questions.

This is **V1 (personal, onlinejobs.ph only)**, built on clean interfaces so **V2 (public, paid, multi-site)** is an extension, not a rewrite.

---

## 2. SLC Framing (Simple, Lovable, Complete)

V1 ships exactly **one loop**, working reliably:

> Every ~5 min, the app runs the owner's saved keyword searches on onlinejobs.ph (logged in), detects new jobs, builds an application package (digest + answered screening questions + ready-to-paste cover letter + tailored resume PDF), and emails a private link. The owner opens it and applies first.

If that loop is reliable and the packages are genuinely good, V1 is a success. Everything else is V2.

---

## 3. Scope

### In scope (V1)
- Single user (the owner). No public signups.
- onlinejobs.ph only.
- Multiple saved keyword searches, polled every ~5 min, newest-first, deduped.
- Authenticated headless scraping (logs in as the owner).
- Onboarding wizard (resume + searches + voice + credentials), **resumable**.
- AI tailoring via a **free LLM** (Gemini), behind a swappable provider, with a rules-based fallback.
- Per-job application package + email notification + private per-job web page.
- Tailored resume PDF (generated from a structured profile + template).
- "Mark applied" / "Skip" status tracking.

### Out of scope (V1 — deferred to V2)
- Multi-user, auth beyond a single app password, billing.
- Any site other than onlinejobs.ph (Upwork is the planned V2 first-add).
- Auto-applying on the owner's behalf.
- Multiple resume profiles / multiple templates.
- Analytics dashboards, mobile app, browser extension.

---

## 4. Locked Decisions

| Area | Decision | Rationale |
|---|---|---|
| Language | Python | Owner preference; great for scraping + AI glue + PDF |
| Runtime | **Oracle Cloud Always Free ARM VM** (Ampere A1, up to 4 OCPU / 24 GB RAM), Docker — **$0/month forever** | 24/7 polling; abundant RAM removes Playwright OOM risk; design identical to a paid VPS |
| Scrape | Playwright (Python), logged-in, per-keyword | Mirrors how the owner searches manually |
| Freshness | Poll every ~5 min, 24/7 | "Apply first" needs near-real-time |
| Data | SQLite (one file) in **WAL mode**, `check_same_thread=False` | Single-user simplicity; WAL allows concurrent worker write + web read; → Postgres in V2 |
| Concurrency | APScheduler (`max_instances=1`) fires the scrape; a **dedicated background worker thread** does tailoring | Slow LLM calls must not block scraping |
| AI | Free LLM API (Gemini default), `LLMProvider` interface, rules fallback | $0 to run; killer feature needs an LLM; swap to paid in V2 |
| PDF | WeasyPrint (HTML template → PDF) | Clean, consistent, template-owned output |
| Email | Resend free tier (Gmail SMTP fallback) | Good deliverability, dev-friendly |
| Web UI | FastAPI + Jinja templates | All-Python, simple, carries into V2 |
| Resume source | Owner fills structured form once; app owns the template | No fragile PDF parsing; regenerate per job |
| Tailoring policy | **Truthful only** — reorder/emphasize/reword existing content; never fabricate | Trust + integrity |

---

## 5. Architecture

### Components (each one responsibility)

| Component | Responsibility | Tech |
|---|---|---|
| **Scheduler** | Fire the scrape every ~5 min, `max_instances=1` | APScheduler (in-process) |
| **JobSource** *(interface)* | Log in, return latest jobs for a keyword, clean up | Playwright; `OnlineJobsPHSource` is the first impl |
| **Detector** | Decide what is genuinely new; dedupe; handle edits | SQLite unique key + content hash |
| **TailoringWorker** | Background thread: pull `DISCOVERED` jobs, build package | thread + in-process queue |
| **TailoringEngine** | Digest, answer screening Qs, cover letter, resume overrides | `LLMProvider` (Gemini) + rules fallback |
| **PdfRenderer** | Structured resume + overrides → PDF | WeasyPrint + HTML/CSS template |
| **Notifier** | Send the alert email with a private link | Resend |
| **WebApp** | Onboarding wizard, dashboard, per-job page, settings, `/healthz` | FastAPI + Jinja |
| **Store** | Persistence | SQLite (SQLModel/SQLAlchemy), WAL |

### Key interfaces (the V2 seams)

```python
class JobSource(Protocol):
    name: str
    def login(self) -> Session: ...           # explicit session object, not implicit instance state
    def search_latest(self, session: Session, keyword: str) -> list[RawJob]: ...
    def close(self, session: Session) -> None: ...   # tear down Playwright browser/context — no leaks

class LLMProvider(Protocol):
    def generate(self, system: str, untrusted_user_text: str, trusted_context: dict) -> str: ...
```

- `OnlineJobsPHSource` and `GeminiProvider` implement these. V2 adds `UpworkSource`, `ClaudeProvider`, etc. with no pipeline change.
- **Session lifecycle is explicit** (Omhar P0): `login()` returns a `Session`; the caller owns it and must `close()` it. Browser context/cookies persist to a Docker volume (`/data/browser_state.json`) so restarts don't trigger a fresh login every time.
- **`generate()` separates untrusted scraped text from trusted profile context** (Custodio P1 — see §9).

### Concurrency model (Omhar P0)
- One APScheduler job runs the scrape loop, `max_instances=1` + `misfire_grace_time` so a slow cycle never overlaps itself.
- Tailoring runs in a **separate daemon thread** consuming an in-process queue of `DISCOVERED` job IDs. SQLite opened with `check_same_thread=False` and `PRAGMA journal_mode=WAL`.

---

## 6. Data Flow

```
Scheduler (every ~5 min, max_instances=1)
  └─ session = JobSource.login() (reuse persisted state)
     for each active SavedSearch:
       JobSource.search_latest(session, keyword)
         └─ Detector: new? ── no → (changed hash? → see edit policy) → drop
                        └ yes → Store Job(status=DISCOVERED); enqueue job_id
     JobSource.close(session)   # or keep warm, but always cleaned on shutdown
TailoringWorker (background thread, consumes queue):
  └─ TailoringEngine.build(job, profile)
       → LLM JSON: digest + screening Q&A + cover_letter + resume_overrides
       → validate against Pydantic schema → on fail: retry ×N → rules fallback
       → PdfRenderer: tailored resume PDF
       → Store Package, Job.status=PACKAGED
Notifier (picks PACKAGED, not yet notified):
  └─ send email w/ private tokenized link → Job.status=NOTIFIED
Owner clicks link → WebApp per-job page (token-checked) → download PDF / copy text
  → "Mark applied" → APPLIED  (invalidates link)   |  "Skip" (+reason) → SKIPPED
```

State is the source of truth, so a crash/restart resumes anything stuck (`DISCOVERED`/`PACKAGED` without notification get reprocessed).

---

## 7. Data Model (SQLite, WAL)

**profile** *(one row in V1)*
`id, full_name, contact_email, alert_email, phone, links(json), target_summary, voice_tone, base_pitch`

**resume_section** *(structured, app-owned)*
`skills(json), experience(json: [{role_id, title, company, start, end, bullets[]}]), education(json), certifications(json), languages(json), tools(json)`

**saved_search**
`id, profile_id, keyword, active(bool), created_at`

**job**
`id, source, external_id, url, title, employer, raw_description(capped ~50KB), posted_at, scraped_at, content_hash, matched_search_id, status, attempts(int, default 0)`
→ **`UNIQUE(source, external_id)`** is the dedupe key (Omhar P1-3 — *not* url). Index: `idx_job_scraped_at ON job(scraped_at DESC)`.

**package**
`id, job_id, digest, fit_summary, screening_qa(json: [{question, drafted_answer}]), compliance_token, cover_letter, resume_overrides(json), resume_pdf_path(server-internal, content-addressed {job_id}/{hash}.pdf), llm_provider, generated_at`

**notification**
`id, job_id, sent_at, link_token (secrets.token_urlsafe(32), unique), expires_at`

**onboarding_state** *(resumable wizard — Manny P2)*
`profile_id, last_completed_step, draft(json)`

**Status enum:** `DISCOVERED → PACKAGED → NOTIFIED → VIEWED → APPLIED | SKIPPED`, plus `UPDATED` (edited repost) and `FAILED` (retryable via `attempts`).

---

## 8. Saved-Search Behavior

- The owner saves **multiple keywords**. Each cycle the scraper runs each active keyword as a newest-first search and reads the top N results.
- **Dedupe across searches:** unique `source+external_id`; a job matching two keywords is stored/emailed once; `matched_search_id` records which keyword surfaced it.
- **Edited-repost policy (Omhar P1-1):** if a job already exists and `content_hash` changed materially, set status `UPDATED` and re-tailor **only if** it was not yet `APPLIED`; never send a second email for the same `external_id` unless the owner hasn't been notified yet. Applied jobs are frozen.
- No filters in V1 (keyword is the filter). Filters are a V2 candidate.

---

## 9. Tailoring Engine (the killer feature) + Injection Safety

**Input:** raw job post (UNTRUSTED) + owner's structured profile (TRUSTED) + voice settings.

**Output contract (strict JSON, validated by a Pydantic model):**
```json
{
  "digest": "2-3 lines: what the employer actually wants",
  "screening_questions": [
    { "question": "extracted instruction/question from the post",
      "drafted_answer": "answer in the owner's voice, using only real background" }
  ],
  "compliance_token": "exact word/phrase the post demands the reply start with, or null",
  "cover_letter": "ready-to-paste message; opens with compliance_token if present; weaves in answers",
  "resume_overrides": {
    "summary": "tailored, truthful summary line",
    "emphasize_skills": ["..."],
    "tailored_bullets": [ { "role_id": "...", "bullets": ["truthful rephrasings"] } ]
  }
}
```

**Rules & safety (Custodio P1 — prompt injection is the top risk):**
- **Trust separation:** the scraped post is passed as a clearly-delimited *untrusted* field, never concatenated into the same instruction string as the profile. The system prompt states the job text is data to analyze, not instructions to follow.
- **Strict validation:** parse → validate against the Pydantic schema → reject any response with fields not in the contract, unexpected URLs, or markup. On failure: retry ×N → rules fallback.
- **No exfil surface:** the LLM call is text-only `generate` — no tools, no HTTP, no email. It cannot act.
- **Render-time escaping:** all LLM/scraped text rendered in Jinja or the PDF is auto-escaped; a post containing `<script>`/markup cannot inject into the page or PDF.
- **Post-gen check:** flag output that contains raw credential strings or fields outside the contract before rendering.
- **Truthful only:** reorder/emphasize/reword existing profile content; never invent jobs, skills, dates, or achievements. This is also a secondary injection containment (limits blast radius).
- **Screening detection priority:** a regex pre-pass ("answer the following", "start your reply with", question marks, numbered lists) ensures embedded questions/compliance tokens are never missed, independent of the LLM.

**Trust UX (Manny P1):**
- If ≥1 screening question is detected, the per-job page shows a **"Review answers before sending"** nudge.
- Resume bullets that were AI-**overridden** are visually flagged vs. base-profile bullets, so the owner verifies nothing was invented at a glance.

**Fallback:** if the LLM is unavailable after retries, the package still ships with regex-detected questions, the raw-post digest, and the base cover letter, marked *"AI draft unavailable — answer manually."* The owner is never blind.

**PDF:** `PdfRenderer` merges base profile + `resume_overrides` into the HTML template via WeasyPrint. Base content is the floor; overrides only re-emphasize. PDF served **only** through the token-checked route (never a static/guessable URL — Omhar/Custodio P1).

---

## 10. UI Surfaces (FastAPI + Jinja)

### Onboarding wizard (one-time, 6 steps, resumable)
1. **Set app password** (public host → must be locked).
2. **Basic info** — name, alert email, phone, portfolio/links.
3. **Your searches** — add keywords as chips; mirror exactly what you type into onlinejobs.ph.
4. **Resume** — summary, skills, repeatable experience, education, optional certifications / languages / tools.
5. **Your voice** — cover-letter tone + base pitch paragraph.
6. **onlinejobs.ph login** — credentials the scraper uses (encrypted; see §13).

Each step persists to `onboarding_state` so a drop mid-wizard resumes where it left off.

### Dashboard
Caught jobs (newest first): title, employer, matched keyword, status badge, time caught, link to per-job page.

### Per-job page (token-guarded)
Employer digest · **screening questions + drafted answers** (copy buttons, "review before sending" nudge) · ready-to-paste **cover letter** · **download tailored resume PDF** (AI-overridden bullets flagged) · link to original post · **"Mark applied" / "Skip (+reason)"**.

### Settings
Edit profile, searches, voice, credentials.

---

## 11. Notification (Email)

- Sent via Resend (Gmail SMTP fallback) the instant a package is ready.
- Subject: `New onlinejobs.ph match: <title> — <employer>`.
- Body: digest, matched keyword, **the first screening question + its drafted answer inline** (Manny P2 — lets the owner judge value from the inbox), and a **private tokenized link** to the per-job page.
- One email per job (guarded by `notification` row + status).

---

## 12. Error Handling & Resilience

| Failure | Handling |
|---|---|
| Session/login expiry | Persist browser state to volume; auto re-login. Alert owner after 3 consecutive login failures. |
| Blocked / captcha | Flag + alert to **phone** (not email). Break-glass fallback: run scraper on owner's home PC in `--remote-scraper` mode that POSTs discovered jobs to the VM API. |
| Duplicate / edited repost | `UNIQUE(source, external_id)`; `content_hash` → `UPDATED` policy (§8). |
| LLM rate-limit / failure | Retry w/ backoff → rules fallback (never blind). |
| Double email | `notification` row + status guard. |
| Crash / restart | Status-driven resume of stuck jobs. |
| Scheduler overlap | `max_instances=1` + `misfire_grace_time`. |
| Silent death (hung process) | `/healthz` returns unhealthy if last scrape > 10 min stale; **UptimeRobot** pings it and alerts the owner's phone. |
| No new jobs in 24h w/ active searches | Dead-man's-switch "system health" email (Manny P2). |
| Disk loss | Daily SQLite backup (`.dump | gzip`) synced off-box to Backblaze B2 free tier via rclone. |
| Log loss | Structured JSON logs to stdout; Docker `max-size=10m max-file=3`. |

---

## 13. Security

- All secrets (onlinejobs.ph login, Gemini key, Resend key, app password hash, credential-encryption key) in `.env` / environment — never committed; `.env.example` documents them.
- onlinejobs.ph credentials **encrypted at rest**. Documented threat model: the encryption key lives on the VM, so **VM compromise = credentials exposed** — acceptable for single-user V1. (V2: off-box secret manager / per-user keys.)
- Per-job link: **128-bit CSPRNG token** (`secrets.token_urlsafe(32)`) + **expiry** (default 30 days; `Mark applied` invalidates early) + `Cache-Control: no-store`. PDF served only via this token-checked route.
- WebApp behind a **single app-password login**: `httpOnly; Secure; SameSite=Strict` session cookie; **rate-limit** (5 fails/IP/10 min → 15-min lockout, `429 Retry-After`); single generic failure message.
- All Jinja-rendered LLM/scraped fields auto-escaped (XSS containment).
- HTTPS via **Caddy** sidecar (`caddy:2-alpine`) with auto-TLS. No HTTP-only exposure.
- `raw_description` capped (~50KB) to prevent disk-fill from oversized posts.

---

## 14. Testing & Validation

- **Phase-0 spike (~1 hr, go/no-go):** prove headless login + reading a keyword search page works from the Oracle VM. If blocked → home-PC fallback before building further.
- **Unit:** job-card parsing, dedupe + edit policy, screening-question regex pre-pass, Pydantic contract validation, PDF renders without layout breakage, token generation.
- **Integration:** saved sample post → full package → test email to the owner; injection test (a post containing fake "system" instructions must not alter output).
- **Soak (1–2 weeks) — concrete go/no-go metrics for V2 (Manny P1):**
  - Time-to-alert: median **< 8 min**, p90 < 12 min.
  - Catch reliability: **≥ 95%** of keyword-matching new jobs caught (spot-check vs manual).
  - Answer quality: owner rates each package 1–3; **avg ≥ 2.5** over **≥ 20** jobs.
  - False-positive rate: **< 25%** (caught then immediately skipped).
  - Reply rate: replies ÷ applications sent (leading willingness-to-pay signal).
  - System uptime **≥ 95%** over the soak.
  - **V2 green light** = quality ≥ 2.5 AND false-positive < 25% AND ≥1 reply AND uptime ≥ 95%.

---

## 15. Cost

| Item | Cost |
|---|---|
| Oracle Cloud Always Free ARM VM | **$0** |
| Gemini / Groq free tier | $0 |
| Resend (≤3k emails/mo) | $0 |
| Backblaze B2 backups (free tier) | $0 |
| SQLite | $0 |
| **Total** | **$0 / month** |

*Oracle signup requires a card for identity verification (~$1 hold, refunded — not a charge). If Oracle won't provision the free VM, the cardless fallback is GitHub Actions (scheduler) + Turso/Supabase (free DB).*

---

## 16. Risks & Open Questions

1. **onlinejobs.ph anti-bot:** datacenter IP may trigger captcha/blocks. *Mitigation:* Phase-0 spike; home-PC fallback; polite pacing; persistent session.
2. **Exact URLs/selectors:** onlinejobs.ph search params (keyword, sort=newest) + DOM selectors unknown until the spike — research task, not a blocker.
3. **Oracle free-tier provisioning:** ARM capacity can be scarce in some regions; signup needs a card. *Mitigation:* retry region/availability domain; GitHub Actions fallback.
4. **Free-tier LLM limits:** Gemini/Groq rate limits during bursts. *Mitigation:* queue + backoff + rules fallback.
5. **ToS / legal:** personal V1 is low-risk; **named gate before V2 monetization** (commercial scraping of a paid platform + CFAA exposure — legal review required).
6. **Resume PDF fidelity:** one polished WeasyPrint template in V1.

---

## 17. V1 → V2 Bridge (no rewrite)

Add later via existing seams: `users` table + real auth, SQLite → Postgres, Stripe/Lemon billing, **Upwork via `JobSource`**, encrypted per-user credentials + off-box key management, paid `ClaudeProvider` (and a `generate_structured` interface), per-user usage limits, search filters, digest emails, skip-reason-driven keyword tuning.

---

## 18. Build Milestones (order)

0. **Spike** — headless login + read a keyword search page on the Oracle VM (go/no-go).
1. **Scraper + Store + Detector** — reliably detect & log new jobs per keyword (no AI); dedupe + edit policy; WAL.
2. **Notifier + per-job page (raw, token-guarded)** — prove the end-to-end loop with raw job data; `/healthz` + uptime ping.
3. **Onboarding + profile** — resumable wizard; structured resume, searches, voice, encrypted credentials.
4. **TailoringEngine + PdfRenderer** — digest, screening Q&A, cover letter, tailored PDF; injection safety; trust UX.
5. **Hardening + soak** — backups, rate-limit, logging; run 1–2 weeks against the §14 metrics; then plan V2.

---

## 19. v1.1 Changelog — Noxa Team Review Incorporated

Resolved from the 2026-06-08 Noxa review (Omhar/Custodio/Gab/Manny):

- **Runtime → Oracle Cloud Always Free VM ($0).** Replaces the $6 VPS; abundant RAM **resolves Gab's P0 OOM risk.**
- **P0 — Concurrency model defined:** dedicated tailoring worker thread, SQLite WAL + `check_same_thread=False`, scheduler `max_instances=1`.
- **P0 — `JobSource` session lifecycle explicit:** `login()→Session`, `close()` teardown, persisted browser state.
- **P1 — Prompt-injection defenses:** trust separation, Pydantic validation, render escaping, no-exfil, post-gen checks.
- **P1 — Link security:** 128-bit token + expiry + `no-store`; PDF only via token route.
- **P1 — LLM JSON validation** via Pydantic; **edited-repost policy** (`UPDATED`); **uniqueness key** clarified to `(source, external_id)`.
- **P1 — Ops:** `/healthz` + UptimeRobot to phone, persisted session, daily off-box SQLite backup, structured logging.
- **P1 — Product:** concrete soak metrics + V2 go/no-go; "review answers" nudge; AI-overridden-bullet flagging; email shows first Q&A inline.
- **P2/P3:** login rate-limiting, `attempts` column, `scraped_at` index, resumable wizard, dead-man's switch, raw-HTML cap, content-addressed PDFs, V2 ToS gate, `generate_structured` for V2.
