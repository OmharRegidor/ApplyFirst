# ApplyFirst — V1 Design Spec

- **Date:** 2026-06-08
- **Status:** Approved for build (pending Noxa team review)
- **Owner:** Omhar (single user for V1)
- **Working name:** ApplyFirst

---

## 1. Problem & Goal

The owner manually refreshes onlinejobs.ph search pages to catch fresh job posts, racing to apply first. Two things lose jobs: (1) not seeing a post quickly enough, and (2) the time it takes to write a tailored application — especially answering the **screening questions** employers bury in posts to filter out mass-appliers.

**Goal:** A personal, always-on web app that watches the owner's onlinejobs.ph searches, and the moment a genuinely-new job appears, builds a complete, ready-to-send application package and emails a private link — so the owner can apply first, with a tailored resume and pre-answered screening questions.

This is **V1 (personal, onlinejobs.ph only)**. It is built on clean interfaces so **V2 (public, paid, multi-site)** is an extension, not a rewrite.

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
- Onboarding wizard (resume + searches + voice + credentials).
- AI tailoring via a **free LLM** (Gemini), behind a swappable provider, with a rules-based fallback.
- Per-job application package + email notification + private per-job web page.
- Tailored resume PDF (generated from a structured profile + template).
- "Mark applied" status tracking.

### Out of scope (V1 — explicitly deferred to V2)
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
| Runtime | Single always-on VPS (Docker), ~$6/mo | 24/7 polling required; Playwright runs naturally |
| Scrape | Playwright (Python), logged-in, per-keyword | Mirrors how the owner searches manually |
| Freshness | Poll every ~5 min, 24/7 | "Apply first" needs near-real-time |
| Data | SQLite (one file) | Single-user simplicity; → Postgres in V2 |
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
| **Scheduler** | Fire the pipeline every ~5 min | APScheduler (in-process) |
| **JobSource** *(interface)* | Log in + return latest jobs for a keyword | Playwright; `OnlineJobsPHSource` is the first impl |
| **Detector** | Decide what is genuinely new; dedupe | SQLite unique key + content hash |
| **TailoringEngine** | Build digest, answer screening Qs, write cover letter, produce resume overrides | `LLMProvider` (Gemini) + rules fallback |
| **PdfRenderer** | Structured resume + overrides → PDF | WeasyPrint + HTML/CSS template |
| **Notifier** | Send the alert email with a private link | Resend |
| **WebApp** | Onboarding wizard, dashboard, per-job page, settings | FastAPI + Jinja |
| **Store** | Persistence | SQLite (SQLModel/SQLAlchemy) |

### Key interfaces (the V2 seams)

```python
class JobSource(Protocol):
    name: str
    def login(self) -> None: ...
    def search_latest(self, keyword: str) -> list[RawJob]: ...

class LLMProvider(Protocol):
    def generate(self, system: str, user: str) -> str: ...  # returns text/JSON
```

`OnlineJobsPHSource` and `GeminiProvider` implement these. V2 adds `UpworkSource`, `ClaudeProvider`, etc. with no change to the pipeline.

---

## 6. Data Flow

```
Scheduler (every ~5 min)
  └─ for each active SavedSearch:
       JobSource.login() (reuse session) → search_latest(keyword)
         └─ Detector: new? ── no → drop
                        └ yes → Store Job(status=DISCOVERED)
TailoringWorker (picks DISCOVERED jobs):
  └─ TailoringEngine.build(job, profile)
       → LLM JSON: digest + screening Q&A + cover_letter + resume_overrides
       → PdfRenderer: tailored resume PDF
       → Store Package, Job.status=PACKAGED
Notifier (picks PACKAGED, not yet notified):
  └─ send email w/ private tokenized link → Job.status=NOTIFIED
Owner clicks link → WebApp per-job page → download PDF / copy text
  → "Mark applied" → Job.status=APPLIED  (or SKIPPED)
```

State is the source of truth, so a crash/restart resumes anything stuck (`DISCOVERED`/`PACKAGED` without notification get reprocessed).

---

## 7. Data Model (SQLite)

**profile** *(one row in V1)*
`id, full_name, contact_email, alert_email, phone, links(json), target_summary, voice_tone, base_pitch`

**resume_section** *(structured, app-owned)*
- `skills(json: string[])`
- `experience(json: [{role_id, title, company, start, end, bullets[]}])`
- `education(json: [...])`
- `certifications(json: string[])`, `languages(json: string[])`, `tools(json: string[])`

**saved_search**
`id, profile_id, keyword, active(bool), created_at`

**job**
`id, source('onlinejobs.ph'), external_id, url (UNIQUE with source), title, employer, raw_description, posted_at, scraped_at, content_hash, matched_search_id, status`

**package**
`id, job_id, digest, fit_summary, screening_qa(json: [{question, drafted_answer}]), compliance_token, cover_letter, resume_overrides(json), resume_pdf_path, llm_provider, generated_at`

**notification**
`id, job_id, sent_at, link_token (unguessable, unique)`

**Status enum:** `DISCOVERED → PACKAGED → NOTIFIED → VIEWED → APPLIED | SKIPPED`, plus `FAILED` (retryable, with `attempts` count).

---

## 8. Saved-Search Behavior

- The owner saves **multiple keywords** (e.g. "virtual assistant", "customer service", "shopify support").
- Each cycle, the scraper runs **each active keyword** as a search on onlinejobs.ph, sorted **newest-first**, and reads the top N results.
- **Dedupe across searches:** a job matching two keywords is stored once (unique `source+external_id`) and emailed once. `matched_search_id` records which keyword first surfaced it.
- No filters in V1 (the keyword is the filter). Filters are a V2 candidate.

---

## 9. Tailoring Engine (the killer feature)

**Input to the LLM:** the raw job post + the owner's structured profile + voice settings.

**Output contract (strict JSON):**
```json
{
  "digest": "2-3 lines: what the employer actually wants",
  "screening_questions": [
    { "question": "extracted instruction/question from the post",
      "drafted_answer": "answer in the owner's voice, using only real background" }
  ],
  "compliance_token": "the exact word/phrase the post demands the reply start with, or null",
  "cover_letter": "ready-to-paste message; opens with compliance_token if present; weaves in answers",
  "resume_overrides": {
    "summary": "tailored, truthful summary line",
    "emphasize_skills": ["..."],
    "tailored_bullets": [ { "role_id": "...", "bullets": ["truthful rephrasings emphasizing job-relevant work"] } ]
  }
}
```

**Rules:**
- **Truthful only.** The LLM may reorder, emphasize, and reword existing profile content. It must **not** invent jobs, skills, dates, or achievements. The system prompt enforces this explicitly.
- **Screening detection is the priority.** The post is scanned (LLM + regex pre-pass for patterns like "answer the following", "start your reply with", question marks, numbered lists) so embedded questions/compliance tokens are never missed.
- **Fallback:** if the LLM is rate-limited/unavailable after retries, the package is still produced with the regex-detected questions, the raw post digest, and the base cover letter, marked *"AI draft unavailable — answer manually."* The owner is never left blind.

**PDF generation:** `PdfRenderer` merges base profile + `resume_overrides` into the HTML template and renders via WeasyPrint. Base content is the floor; overrides only re-emphasize.

---

## 10. UI Surfaces (FastAPI + Jinja)

### Onboarding wizard (one-time, 6 steps)
1. **Set app password** (the app is on a public VPS).
2. **Basic info** — name, alert email, phone, portfolio/links.
3. **Your searches** — add keywords as chips; these mirror exactly what the owner types into onlinejobs.ph.
4. **Resume** — summary, skills, repeatable experience (title/company/dates/bullets), education, plus optional certifications / languages / tools.
5. **Your voice** — cover-letter tone + a base pitch paragraph the AI adapts per job.
6. **onlinejobs.ph login** — credentials the scraper uses (stored securely).

### Dashboard
List of caught jobs (newest first) with: title, employer, matched keyword, status badge, time caught, and a link to the per-job page.

### Per-job page (opened from the email link)
- Employer posting digest
- Extracted **screening questions with drafted answers** (copy buttons)
- Ready-to-paste **cover letter** (copy button)
- **Download tailored resume PDF**
- Link out to the original post + **"Mark applied" / "Skip"** buttons

### Settings
Edit profile, searches, voice, credentials.

---

## 11. Notification (Email)

- Sent via Resend (Gmail SMTP fallback) the instant a package is ready.
- Subject: `New onlinejobs.ph match: <title> — <employer>`.
- Body: digest, the matched keyword, a count of screening questions answered, and a **private tokenized link** to the per-job page.
- One email per job (guarded by the `notification` row + status). Optional future: a digest mode.

---

## 12. Error Handling & Resilience

| Failure | Handling |
|---|---|
| Session/login expiry | Persist cookies; auto re-login. Alert owner after 3 consecutive login failures. |
| Blocked / captcha | Flag loudly + alert. Fallback: run scraper on owner's always-on home PC. |
| Duplicate / edited repost | Unique `source+external_id`; `content_hash` catches material edits. |
| LLM rate-limit / failure | Retry with backoff; then rules fallback package (never blind). |
| Double email | `notification` row + status guard. |
| Crash / restart | Status-driven resume of stuck jobs. |
| Scraper partial parse | Store raw HTML; log + skip the unparseable card, continue others. |

---

## 13. Security

- All secrets (onlinejobs.ph login, Gemini key, Resend key, app password hash) in `.env` / environment — never committed.
- onlinejobs.ph credentials stored encrypted at rest (V1: app-level encryption; V2: per-user encryption).
- Per-job link uses an **unguessable token** (it exposes resume + personal data).
- WebApp behind a **single app-password login** (it lives on a public VPS).
- HTTPS via reverse proxy (Caddy/Traefik) with auto-TLS.

---

## 14. Testing Strategy

- **Phase-0 spike (~1 hr, go/no-go):** prove headless login + reading a keyword search result page works from the VPS. If blocked, switch scraper host to home PC before building further.
- **Unit:** job-card parsing, dedupe logic, screening-question regex pre-pass, PDF renders without layout breakage, LLM JSON-contract validation.
- **Integration:** saved sample post HTML → full package → test email to the owner.
- **Soak:** run live 1–2 weeks; measure: jobs caught, time-to-alert, answer quality, false positives.

---

## 15. Cost

| Item | Cost |
|---|---|
| VPS (1–2 GB, Docker) | ~$5–6/mo |
| Gemini / Groq free tier | $0 |
| Resend (≤3k emails/mo) | $0 |
| SQLite | $0 |
| **Total** | **≈ $6/mo** |

---

## 16. Risks & Open Questions

1. **onlinejobs.ph anti-bot:** datacenter IP may trigger captcha/blocks. *Mitigation:* Phase-0 spike; home-PC fallback; polite pacing; persistent session.
2. **Exact URLs/selectors:** onlinejobs.ph search URL params (keyword, sort=newest) and DOM selectors are unknown until the spike — a research task, not a blocker.
3. **Free-tier LLM limits:** Gemini/Groq rate limits during bursts. *Mitigation:* queue + backoff + rules fallback.
4. **ToS:** personal automated use is low-risk; revisit before charging money in V2.
5. **Resume PDF fidelity:** WeasyPrint template must look professional — one polished template in V1.

---

## 17. V1 → V2 Bridge (no rewrite)

Add later via existing seams: `users` table + real auth, SQLite → Postgres, Stripe/Lemon billing, **Upwork via `JobSource`**, encrypted per-user credentials, paid `ClaudeProvider` for quality, per-user usage limits, search filters, digest emails.

---

## 18. Build Milestones (order)

0. **Spike** — headless login + read a keyword search page (go/no-go).
1. **Scraper + Store + Detector** — reliably detect & log new jobs per keyword (no AI).
2. **Notifier + per-job page (raw)** — prove the end-to-end loop with raw job data.
3. **Onboarding + profile** — structured resume, searches, voice, credentials.
4. **TailoringEngine + PdfRenderer** — digest, screening Q&A, cover letter, tailored PDF.
5. **Polish + soak** — run 1–2 weeks, measure, then plan V2.
