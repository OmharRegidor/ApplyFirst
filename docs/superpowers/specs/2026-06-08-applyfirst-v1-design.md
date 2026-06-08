# ApplyFirst — V1 Design Spec

- **Date:** 2026-06-08
- **Version:** 1.2 (Phase-0 spike passed → architecture simplified: no login, no browser)
- **Status:** ✅ Build-ready · Milestone 0 (spike) COMPLETE
- **Owner:** Omhar (single user for V1)
- **Working name:** ApplyFirst
- **Repo:** https://github.com/OmharRegidor/ApplyFirst

> Changelog at the end (§19). v1.1 folded in the Noxa review; v1.2 folds in the spike result.

---

## 0. Phase-0 Spike Result (2026-06-08) — PASSED ✅

Validated live against onlinejobs.ph:
- **Job search is fully public** — no login. URL: `…/jobseekers/jobsearch?jobkeyword=<kw>`; 30 jobs/page; **already sorted newest-first**; pagination present.
- **Each job card** has a URL ending in a **numeric ID** (`/jobseekers/job/<slug>-<id>`) → ideal dedupe key — plus title, employment type, exact **`Posted on YYYY-MM-DD HH:MM:SS`** timestamp, and salary.
- **Job detail pages are fully public** — full description visible without login, including the **"TO APPLY" screening questions** (confirmed a real one in the wild: *"To show you read this post, tell me: what is your favorite hobby?"*).
- **Plain HTTP works (no browser):** a `GET` with a normal User-Agent returned **200 / 183 KB / 30 jobs** from a datacenter IP. No JS rendering or login required for detection *or* descriptions.
- Login is required **only to apply** — which the owner does manually.

**Consequence:** V1 needs **no Playwright, no login, and no stored credentials.** Detection + packaging run entirely on public HTTP reads.

---

## 1. Problem & Goal

The owner manually refreshes onlinejobs.ph searches to catch fresh posts, racing to apply first. Two things lose jobs: (1) not seeing a post quickly enough, and (2) the time to write a tailored application — especially answering the **screening questions** employers bury in posts to filter out mass-appliers.

**Goal:** A personal, always-on app that watches the owner's onlinejobs.ph searches, and the moment a genuinely-new job appears, builds a complete, ready-to-send application package and emails a private link — so the owner applies first, with a tailored resume and pre-answered screening questions.

V1 = personal, onlinejobs.ph only, built on clean interfaces so V2 (public, paid, multi-site) is an extension, not a rewrite.

---

## 2. SLC Framing (Simple, Lovable, Complete)

One loop, working reliably:
> Every ~5 min, fetch the owner's saved keyword searches on onlinejobs.ph (public HTTP), detect new jobs, build an application package (digest + answered screening questions + ready-to-paste cover letter + tailored resume PDF), and email a private link. The owner opens it and applies first.

---

## 3. Scope

### In scope (V1)
- Single user. No public signups.
- onlinejobs.ph only, **public reads** (no login, no credentials).
- Multiple saved keyword searches, polled every ~5 min, newest-first, deduped by job ID.
- Onboarding wizard (resume + searches + voice), **resumable**.
- AI tailoring via a **free LLM** (Gemini), swappable provider, rules fallback.
- Per-job package + email notification + private per-job web page.
- Tailored resume PDF from a structured profile + template.
- "Mark applied" / "Skip" tracking.

### Out of scope (V1 → V2)
Multi-user/auth/billing · sites other than onlinejobs.ph (Upwork first in V2) · auto-applying · multiple resume profiles · analytics · mobile app · browser extension.

---

## 4. Locked Decisions

| Area | Decision | Rationale |
|---|---|---|
| Language | Python | Owner preference; great for fetch/parse + AI + PDF |
| Runtime | Oracle Cloud Always Free VM, Docker — **$0/mo** | 24/7; no browser → tiny footprint, runs on the smallest free box |
| Scrape | **Public HTTP fetch + HTML parse** (`httpx` + `selectolax`/BeautifulSoup), per-keyword — **no login, no browser** | Proven in spike; minimal RAM; no credential risk |
| Freshness | Poll every ~5 min, 24/7, **polite** (jittered interval, backoff, cached ETag/If-Modified) | "Apply first" + good-citizen reads |
| Data | SQLite (one file) in WAL mode, `check_same_thread=False` | Single-user; WAL = concurrent worker write + web read; → Postgres in V2 |
| Concurrency | APScheduler (`max_instances=1`) polls; **dedicated worker thread** does tailoring | Slow LLM calls must not block polling |
| AI | Free LLM (Gemini default), `LLMProvider` interface, rules fallback | $0; killer feature needs an LLM; swap to paid in V2 |
| PDF | WeasyPrint (HTML template → PDF) | Clean, consistent, template-owned |
| Email | Resend free tier (Gmail SMTP fallback) | Deliverability, dev-friendly |
| Web UI | FastAPI + Jinja | All-Python, simple, carries to V2 |
| Resume source | Owner fills structured form once; app owns the template | No fragile PDF parsing |
| Tailoring policy | **Truthful only** — reorder/emphasize/reword; never fabricate | Trust + integrity |

---

## 5. Architecture

### Components

| Component | Responsibility | Tech |
|---|---|---|
| **Scheduler** | Fire the poll every ~5 min, `max_instances=1` | APScheduler |
| **JobSource** *(interface)* | Fetch latest jobs for a keyword; fetch a job's full detail | `httpx` + HTML parser; `OnlineJobsPHSource` first impl |
| **Detector** | Decide what is genuinely new; dedupe; handle edits | SQLite unique key + content hash |
| **TailoringWorker** | Background thread: pull `DISCOVERED` jobs, build package | thread + in-process queue |
| **TailoringEngine** | Digest, answer screening Qs, cover letter, resume overrides | `LLMProvider` (Gemini) + rules fallback |
| **PdfRenderer** | Structured resume + overrides → PDF | WeasyPrint |
| **Notifier** | Send the alert email with a private link | Resend |
| **WebApp** | Onboarding, dashboard, per-job page, settings, `/healthz` | FastAPI + Jinja |
| **Store** | Persistence | SQLite (SQLModel/SQLAlchemy), WAL |

### Key interfaces (V2 seams)

```python
class JobSource(Protocol):
    name: str
    def search_latest(self, keyword: str) -> list[RawJob]: ...   # parse search results page(s)
    def fetch_detail(self, job: RawJob) -> JobDetail: ...         # parse full description + apply section

class LLMProvider(Protocol):
    def generate(self, system: str, untrusted_user_text: str, trusted_context: dict) -> str: ...
```

- `OnlineJobsPHSource` + `GeminiProvider` implement these; V2 adds `UpworkSource`, `ClaudeProvider`, etc. with no pipeline change.
- **No session/login** — both methods are stateless public GETs (polite headers, jitter, backoff).
- `generate()` keeps untrusted scraped text separate from trusted profile context (§9).

### Concurrency
One APScheduler poll job (`max_instances=1` + `misfire_grace_time`); tailoring runs in a separate daemon thread off an in-process queue. SQLite WAL + `check_same_thread=False`.

---

## 6. Data Flow

```
Scheduler (~5 min, max_instances=1)
  └─ for each active SavedSearch:
       JobSource.search_latest(keyword)          # GET search page, parse cards (id,url,title,type,posted_at,salary)
         └─ Detector: new id? ── no (hash changed? → edit policy) → drop
                        └ yes → Store Job(status=DISCOVERED); enqueue id
TailoringWorker (background thread):
  └─ JobSource.fetch_detail(job)                 # GET detail page, parse full description + "TO APPLY"
     TailoringEngine.build(detail, profile)
       → LLM JSON: digest + screening Q&A + cover_letter + resume_overrides
       → validate (Pydantic) → retry ×N → rules fallback
       → PdfRenderer → tailored PDF
       → Store Package, Job.status=PACKAGED
Notifier (PACKAGED, not notified):
  └─ email + private tokenized link → NOTIFIED
Owner clicks link → per-job page (token-checked) → copy text / download PDF
  → "Mark applied" → APPLIED (invalidates link)  |  "Skip"(+reason) → SKIPPED
```
Status is the source of truth → crash/restart resumes stuck jobs.

---

## 7. Data Model (SQLite, WAL)

**profile** *(one row)* — `id, full_name, contact_email, alert_email, phone, links(json), target_summary, voice_tone, base_pitch`
*(No onlinejobs.ph credentials — none needed.)*

**resume_section** — `skills(json), experience(json:[{role_id,title,company,start,end,bullets[]}]), education(json), certifications(json), languages(json), tools(json)`

**saved_search** — `id, profile_id, keyword, active(bool), created_at`

**job** — `id, source, external_id, url, title, employer, employment_type, salary_text, raw_description(capped ~50KB), posted_at, scraped_at, content_hash, matched_search_id, status, attempts(int)`
→ **`UNIQUE(source, external_id)`** is the dedupe key. Index `idx_job_scraped_at ON job(scraped_at DESC)`.

**package** — `id, job_id, digest, fit_summary, screening_qa(json:[{question,drafted_answer}]), compliance_token, cover_letter, resume_overrides(json), resume_pdf_path(server-internal, content-addressed), llm_provider, generated_at`

**notification** — `id, job_id, sent_at, link_token (secrets.token_urlsafe(32), unique), expires_at`

**onboarding_state** — `profile_id, last_completed_step, draft(json)`

**Status:** `DISCOVERED → PACKAGED → NOTIFIED → VIEWED → APPLIED | SKIPPED`, plus `UPDATED` (edited repost) and `FAILED` (retryable via `attempts`).

---

## 8. Saved-Search Behavior
- Multiple keywords; each cycle fetches each active keyword's newest-first search page and reads top-N cards.
- **Dedupe** by `source+external_id` (the numeric job ID); a job matching two keywords is stored/emailed once; `matched_search_id` records the first keyword that surfaced it.
- **Edited-repost policy:** if `content_hash` changed and the job isn't `APPLIED`, set `UPDATED` + re-tailor; never a second email for the same id once notified. Applied jobs frozen.
- No filters in V1 (keyword is the filter). onlinejobs.ph *does* expose employment-type checkboxes — a V2 candidate.

---

## 9. Tailoring Engine (killer feature) + Injection Safety

**Input:** the job's full description (UNTRUSTED) + structured profile (TRUSTED) + voice.

**Output (strict JSON, Pydantic-validated):**
```json
{
  "digest": "2-3 lines: what the employer wants",
  "screening_questions": [{ "question": "extracted from the TO APPLY/instructions", "drafted_answer": "in the owner's voice, real background only" }],
  "compliance_token": "exact word/phrase the post demands the reply open with, or null",
  "cover_letter": "ready-to-paste; opens with compliance_token if present; weaves in answers",
  "resume_overrides": { "summary": "tailored, truthful", "emphasize_skills": ["..."], "tailored_bullets": [{ "role_id": "...", "bullets": ["truthful rephrasings"] }] }
}
```

**Rules & safety (prompt injection is the top remaining risk):**
- **Trust separation:** scraped text passed as a delimited *untrusted* field; system prompt says it is data to analyze, not instructions to obey.
- **Strict validation:** parse → Pydantic → reject unexpected fields/URLs/markup → retry ×N → rules fallback.
- **No exfil surface:** text-only `generate`, no tools/HTTP/email.
- **Render escaping:** all LLM/scraped text auto-escaped in Jinja + PDF.
- **Truthful only:** reorder/emphasize/reword existing content; never invent — also limits injection blast radius.
- **Screening detection priority:** regex pre-pass ("to apply", "please reply with", "start your reply with", numbered lists, "?") guarantees questions/compliance tokens aren't missed even if the LLM slips.

**Trust UX:** if ≥1 screening question detected, per-job page shows a **"Review answers before sending"** nudge; AI-**overridden** resume bullets are visually flagged vs base.

**Fallback:** LLM down → package still ships with regex-detected questions + raw digest + base cover letter, marked *"AI draft unavailable — answer manually."*

**PDF:** WeasyPrint merges base profile + overrides; served **only** via the token-checked route (never a guessable file URL).

---

## 10. UI Surfaces (FastAPI + Jinja)

### Onboarding wizard (one-time, **5 steps**, resumable)
1. **Set app password** (public host → locked).
2. **Basic info** — name, alert email, phone, links.
3. **Your searches** — keyword chips mirroring what you type into onlinejobs.ph.
4. **Resume** — summary, skills, experience, education, optional certifications / languages / tools.
5. **Your voice** — cover-letter tone + base pitch paragraph.

*(No credentials step — V1 never logs in.)* Each step persists to `onboarding_state`.

### Dashboard
Caught jobs (newest first): title, employer, matched keyword, status, time caught, link.

### Per-job page (token-guarded)
Digest · **screening Q&A** (copy buttons + "review before sending") · ready-to-paste **cover letter** · **download tailored PDF** (AI bullets flagged) · link to original post · **Mark applied / Skip(+reason)**.

### Settings
Edit profile, searches, voice.

---

## 11. Notification (Email)
Resend (Gmail SMTP fallback), sent the instant a package is ready. Subject `New onlinejobs.ph match: <title> — <employer>`. Body: digest, matched keyword, **first screening Q + drafted answer inline**, private tokenized link. One email per job (notification row + status guard).

---

## 12. Error Handling & Resilience

| Failure | Handling |
|---|---|
| Fetch error / non-200 / IP rate-limit | Backoff + jitter; retry next cycle; alert phone after N consecutive failures. Polite interval to avoid blocks. |
| HTML structure change (selectors break) | Parser fails soft per-card, logs raw HTML sample, alerts; never crashes the loop. |
| Duplicate / edited repost | `UNIQUE(source, external_id)`; `content_hash` → `UPDATED` (§8). |
| LLM rate-limit / failure | Retry + backoff → rules fallback (never blind). |
| Double email | notification row + status guard. |
| Crash / restart | Status-driven resume of stuck jobs. |
| Scheduler overlap | `max_instances=1` + `misfire_grace_time`. |
| Silent death (hung process) | `/healthz` unhealthy if last poll > 10 min stale; **UptimeRobot** pings → alerts owner's **phone**. |
| No new jobs in 24h w/ active searches | Dead-man's-switch "system health" email. |
| Disk loss | Daily SQLite backup (`.dump | gzip`) → Backblaze B2 free tier via rclone. |
| Log loss | Structured JSON logs to stdout; Docker `max-size=10m max-file=3`. |

---

## 13. Security
- Secrets (Gemini key, Resend key, app-password hash) in `.env` / env — never committed; `.env.example` documents them. **No third-party login to store.**
- Sensitive data = the owner's own profile/resume + generated packages. Per-job link: **128-bit token** (`secrets.token_urlsafe(32)`) + **expiry** (default 30 days; `Mark applied` invalidates) + `Cache-Control: no-store`; PDF served only via token route.
- WebApp behind a **single app-password login**: `httpOnly; Secure; SameSite=Strict` cookie; **rate-limit** (5 fails/IP/10 min → 15-min lockout, `429`); generic failure message.
- All Jinja-rendered LLM/scraped fields auto-escaped (XSS containment).
- HTTPS via **Caddy** sidecar (auto-TLS). No HTTP-only exposure.
- `raw_description` capped (~50KB).
- **Polite scraping / ToS:** identify a sane User-Agent, respect `robots.txt`, conservative interval + caching; public reads only. Re-confirm ToS posture before any V2 monetization (named gate).

---

## 14. Testing & Validation
- **Phase-0 spike — DONE ✅** (§0).
- **Unit:** search-card parsing, detail parsing, dedupe + edit policy, screening regex pre-pass, Pydantic contract validation, PDF render, token generation.
- **Integration:** saved sample HTML → full package → test email; injection test (a post with fake "system" instructions must not alter output).
- **Soak (1–2 weeks) — go/no-go metrics for V2:**
  - Time-to-alert: median **< 8 min**, p90 < 12 min.
  - Catch reliability: **≥ 95%** of keyword-matching new jobs caught (spot-check vs manual).
  - Answer quality: owner rates each package 1–3; **avg ≥ 2.5** over **≥ 20** jobs.
  - False-positive: **< 25%** (caught then immediately skipped).
  - Reply rate: replies ÷ applications sent.
  - Uptime **≥ 95%**.
  - **V2 green light** = quality ≥ 2.5 AND false-positive < 25% AND ≥1 reply AND uptime ≥ 95%.

---

## 15. Cost
| Item | Cost |
|---|---|
| Oracle Cloud Always Free VM | $0 |
| Gemini / Groq free tier | $0 |
| Resend (≤3k emails/mo) | $0 |
| Backblaze B2 backups | $0 |
| SQLite | $0 |
| **Total** | **$0 / month** |

*Oracle signup needs a card for ID verification (~$1 hold, refunded). Cardless fallback: GitHub Actions (scheduler) + Turso/Supabase (DB) — even easier now that no browser is required.*

---

## 16. Risks & Open Questions
1. **Read rate-limiting / IP block:** mild for polite public GETs; mitigated by jitter, backoff, caching, sane interval. (Spike showed datacenter IP reads fine.)
2. **HTML structure changes:** onlinejobs.ph could change markup; mitigated by soft-fail parsing + alerts + a small parser test suite.
3. **Oracle free-tier provisioning:** ARM/AMD capacity can be scarce; needs a card. *Mitigation:* retry region; GitHub Actions fallback.
4. **Free-tier LLM limits:** burst rate limits; queue + backoff + rules fallback.
5. **ToS / legal:** public personal reads are low-risk; **named gate before V2 monetization.**
6. **Resume PDF fidelity:** one polished WeasyPrint template in V1.

---

## 17. V1 → V2 Bridge (no rewrite)
`users` + auth · SQLite → Postgres · billing · **Upwork via `JobSource`** · paid `ClaudeProvider` (+ `generate_structured`) · per-user usage limits · employment-type/salary filters · digest emails · skip-reason-driven keyword tuning.

---

## 18. Build Milestones
0. **Spike — DONE ✅** (public fetch + parse proven).
1. **Scraper + Store + Detector** — `OnlineJobsPHSource.search_latest` (HTTP+parse), SQLite (WAL) schema, dedupe + edit policy, runnable poll CLI. *(No AI, no web yet.)*
2. **Notifier + per-job page (raw, token-guarded)** — `fetch_detail`, email, FastAPI page, `/healthz` + uptime ping. Prove the end-to-end loop with raw data.
3. **Onboarding + profile** — resumable 5-step wizard; structured resume, searches, voice.
4. **TailoringEngine + PdfRenderer** — digest, screening Q&A, cover letter, tailored PDF; injection safety; trust UX.
5. **Hardening + soak** — backups, rate-limit, logging; run 1–2 weeks vs §14 metrics; then plan V2.

---

## 19. Changelog
**v1.2 (spike result):** Job search + detail pages are public; plain HTTP works from a datacenter IP. **Removed Playwright, login, and all stored credentials** from V1. Scrape = `httpx` + HTML parse. Onboarding dropped to 5 steps (no credentials). Security simplified (no third-party creds; prompt-injection + XSS escaping remain). Risks reduced to mild read rate-limiting + HTML drift. Added polite-scraping/ToS guidance. Milestone 0 marked complete.

**v1.1 (Noxa review):** Oracle free host ($0); concurrency model; explicit interfaces; prompt-injection defenses; token entropy/expiry + safe PDF serving; Pydantic LLM validation; edit policy; ops monitoring; concrete soak metrics; trust UX; P2/P3 fixes.
