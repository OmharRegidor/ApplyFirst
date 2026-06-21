# M3 — Multi-Tenant Polling Worker — Plan

- **Owner:** Omhar (solo)
- **Status:** 🟡 PLANNED → building
- **Design parent:** `docs/SYSTEM-DESIGN.md` §7 (worker state machine), §8 (cost/safety). Detailed design from the M3 understand-workflow (reuse map + Gmail recipe + db v3) — `.noxa/m3-worker/`.
- **Builds on:** M1 (auth) + M2 (onboarding + encrypted gmail.send token), commit af04994.
- **Goal:** a worker that polls onlinejobs.ph once per unique keyword across all tenants, fans out per-tenant alerts, tailors each application, and **sends it via the Gmail API to the user's own inbox** — with a daily cap, a tailoring cache, and a dead-man's switch. This is the milestone that makes ApplyFirst actually *do the thing*.

## 1. Done-when
- [ ] `python -m applyfirst.saas.worker --once` runs one deterministic cycle; the long-running form loops with jitter.
- [ ] Shared poll: each unique active keyword across all activated tenants is fetched **once**; jobs stored in a cross-tenant `jobs` table (dedupe by `onlinejobs_id`).
- [ ] First poll of a keyword **baselines** silently (no alerts) — no backlog flood.
- [ ] Per-tenant fan-out: a `user_job_alerts` row per (activated user, new job) for their matching keyword; never alerted twice (`UNIQUE(user_id, job_id)`).
- [ ] Per pending alert: enforce a **daily cap** (atomic), tailor (Gemini if `GEMINI_API_KEY` set, else rules-fallback), reuse the **(job_id, profile_hash) cache**, then **send via Gmail** to the user's own inbox; mark `sent`/`failed`/`capped`/`skipped`.
- [ ] **Refresh token decrypted in memory only** (AAD=user_id), never logged. `invalid_grant`/insufficient-scope → clear the user's gmail credential (stop retrying), mark the alert failed.
- [ ] **Per-(user,job) isolation**: each tailoring call sees exactly one user's profile + one public job — no cross-tenant context to Gemini.
- [ ] Dead-man's switch: a worker heartbeat + consecutive-empty/failure detection logs a CRITICAL event for the owner (not tenants).
- [ ] All existing tests pass; new tests cover gmail_send (mocked), db v3, and a full `run_once` cycle (injected fake source/engine/sender).
- [ ] CLI + `applyfirst.db` untouched.

## 2. Out of scope (deferred)
- M4: Google app-verification submission.
- M5: owner **email** alerting (M3 uses a heartbeat + CRITICAL log), `/auth/*` rate-limit, nightly backup, daily-cap dashboard banner.
- Later: tailored **resume PDF** attachment (needs a richer profile than the 4 fields; the email carries the cover letter + screening answers).
- M6: Postgres.

## 3. Reuse (from the understand workflow) — import as-is
- `applyfirst.sources.onlinejobsph.OnlineJobsPHSource` — `search_latest(keyword)→list[RawJob]`, `fetch_detail(job)→JobDetail`.
- `applyfirst.sources.base.make_client`, `JobSource` (Protocol); `applyfirst.models.RawJob/JobDetail`.
- `applyfirst.tailor.GeminiProvider`, `TailoringEngine` (provider=None → rules fallback).
- `applyfirst.notify.compose.build_tailored_email(job, package, ai_available)` → (subject, text, html).
- `applyfirst.saas.preview` profile-mapping (4 fields → `applyfirst.profile.Profile`) — refactor to a shared `to_profile()`.
- **NOT reused** (CLI-store-coupled): `store.py`, `detector.py`, `pipeline.py` — the worker re-implements multi-tenant dedup/fanout against the SaaS DB.

## 4. File map
```
applyfirst/saas/
  gmail_send.py   # NEW — get_access_token + send_email; GmailSendError / GmailAuthError
  worker.py       # NEW — run_once + process_alert + daemon main + purge + dead-man's switch
  db.py           # MOD — _migrate_v3 (jobs, user_job_alerts, ai_usage, tailoring_cache, worker_keyword_state, worker_meta); helpers; TENANT_TABLES += user_job_alerts, ai_usage
  config.py       # MOD — gemini_api_key, gemini_model, daily_tailor_cap, worker_interval, worker_jitter
  preview.py      # MOD — extract to_profile() for reuse by the worker
tests/
  test_saas_gmail_send.py  # NEW — token refresh + send (mocked httpx); invalid_grant→GmailAuthError
  test_saas_db_v3.py       # NEW — migration, job upsert/dedupe, fanout, atomic cap, cache, baseline
  test_saas_worker.py      # NEW — full run_once with fake source/engine/sender; cap; cache; isolation; invalid_grant→disconnect
```

## 5. Steps
1. `gmail_send.py` (+ tests) — standalone, no DB.
2. db v3 migration + helpers (+ tests).
3. `preview.to_profile()` refactor.
4. `worker.py` run_once/process_alert/daemon/dead-man (+ config fields) (+ tests).
5. Gauntlet: py_compile + full pytest; verify-and-fix wave (Custodio security + Franco QA); re-gate.

## 6. Security must-dos (Custodio lens, from design)
Per-(user,job) isolation; decrypt-in-memory-only (never logged, never in `last_error`); tenant-scoped alert/usage reads; `invalid_grant`→clear credential (no infinite retry, bounded `attempts`); AAD=user_id on decrypt; dead-man's switch → owner only.

## Changelog
- **2026-06-21** — v0.1. Design from the M3 understand-workflow; scraper reuse confirmed in `applyfirst/sources/`. Real Gmail send + polling land here; resume-PDF + owner-email-alerting deferred.
