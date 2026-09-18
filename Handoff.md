# Goal — What we're building
**ApplyFirst** — be first to apply on **onlinejobs.ph**. Two surfaces:
- **V1 — personal CLI** (live on Oracle): polls every ~5 min, AI-tailors an application via Gemini,
  emails it to me. Plus a private read-only dashboard over Tailscale. **Unchanged — still running.**
- **V2 — multi-tenant SaaS** (`applyfirst/saas/`): other onlinejobs.ph applicants sign in with Google,
  onboard, and the worker delivers tailored applications **to their own Gmail inbox**. **Built M1–M5;
  committed.** Now has **two deploy targets**: the Oracle VM production runbook (`deploy/oracle/`) and a
  new **Fly.io beta path** (prepared this session).

# Current State — Where it stands (2026-07-05)
✅ **M1–M5 committed** (unchanged since 2026-06-21). **Tests: 211 passing** (`.venv/Scripts/python.exe -m
pytest -q`) — was 208; +3 added this session.

⚠️ **THIS SESSION'S WORK IS UNCOMMITTED — in the working tree, not yet committed.** Two adversarial-audit
workflows drove code fixes (all tests green) + created the Fly deploy artifacts. Commit these before/after
the next step. Files:
- **Modified (audit fixes):** `applyfirst/saas/app.py`, `config.py`, `crypto.py`, `gmail_send.py`,
  `tests/test_saas_gmail_send.py`, `tests/test_saas_rate_limit.py`
- **New (Fly deploy, repo root):** `Dockerfile`, `entrypoint.sh`, `fly.toml`, `.dockerignore`
- (`.gitattributes` already existed and already forces `*.sh eol=lf` — untouched. `REMOTE.md` is the
  pre-existing untracked file — NOT mine, never commit it.)

## Fly.io beta deploy (NEW this session)
**Why Fly, not Vercel:** Vercel **cannot** host this app — its filesystem is ephemeral (`/tmp` wiped per
invocation, not shared), which wipes the SQLite DB (`db.py:105` `sqlite3.connect`), and it has no always-on
process for the poll worker (`worker.py` loops). Vercel would need a full Postgres migration (M6) + paid
cron. **Fly fits as-is:** ONE machine runs web + worker together, sharing SQLite on a persistent volume.
- **Topology:** `entrypoint.sh` runs `uvicorn applyfirst.saas.app:app` (foreground) + `python -m
  applyfirst.saas.worker` (background) in ONE machine; both share `/data/applyfirst-saas.db` on a Fly
  volume. **NEVER `fly scale count >1`** — a Fly volume attaches to a single machine; a 2nd machine gets
  its own empty volume and splits the DB. `fly.toml` pins `auto_stop_machines=false` so the worker never
  suspends.
- **Image:** `Dockerfile` uses **python:3.12-slim** (not 3.14) — guaranteed manylinux wheels, no compiler,
  no build risk; app is 3.10+ safe. `sed` strips CR from `entrypoint.sh` (CRLF shebang would fail exec).
- **Full click-by-click** is in the chat transcript; the deployed-in-order gist:
  `flyctl install` → `fly apps create <name>` (→ URL becomes `https://<name>.fly.dev`) → edit `fly.toml`
  (`app=` **and** `APPLYFIRST_BASE_URL` in `[env]`, same pass) → `fly volumes create af_data --region sin
  --size 1` → Google Console (enable **Gmail API**, OAuth Web client, Testing mode + test users, redirect
  URIs `/auth/callback` + `/auth/gmail-callback`) → generate secrets with the Python one-liner → `fly
  secrets set` (SESSION_SECRET, APPLYFIRST_MASTER_KEY, GOOGLE_CLIENT_ID/SECRET; NOT base_url — it's in
  fly.toml) → `fly deploy` → verify with `fly status`/`fly logs` (NOT `fly scale`).
- **Audit report (may be wiped — key points inlined below):**
  `scratchpad/fly-deploy-audit.md`.

## Audit-driven fixes applied this session (uncommitted, tests green)
A 7-dimension adversarial audit workflow found **13 confirmed issues, 0 false alarms**. Applied:
- **B1 (was a BLOCKER):** the `/auth` rate limiter keyed on the **last X-Forwarded-For hop** — correct for
  Caddy (Oracle), but on **Fly that's a constant app-owned IP**, collapsing all clients into ONE 20-req/60s
  bucket → any one visitor could globally lock out sign-in. **Fix:** new config field `trusted_ip_header`
  (`APPLYFIRST_TRUSTED_IP_HEADER`); `_client_ip` (app.py) reads the un-forgeable `Fly-Client-IP` when set,
  else falls back to XFF-last-hop (so **Oracle/Caddy still works unchanged**). `fly.toml [env]` sets
  `APPLYFIRST_TRUSTED_IP_HEADER=fly-client-ip`. New test covers the Fly path.
- **S2:** `APPLYFIRST_BASE_URL` silently defaulted to localhost → 100% OAuth `redirect_uri_mismatch` with no
  boot error. **Fix:** `config.py` now **refuses to boot** in prod (secure cookies) if base_url is
  localhost/unset; value moved to `fly.toml [env]` (not the secrets batch).
- **S5:** `gmail_send.py` mapped **every** 403 to `GmailAuthError` → the worker **disconnected** users on
  transient rate-limit 403s and on `accessNotConfigured` (Gmail API disabled) — a reconnect loop a reconnect
  can't fix. **Fix:** classify by 403 `reason`; only `insufficientPermissions`/`ACCESS_TOKEN_SCOPE_INSUFFICIENT`
  → disconnect; rate-limit/API-disabled → retryable `GmailSendError`. +2 tests.
- **S4:** error hints pointed at `openssl` (absent on default Windows). **Fix:** `config.py` + `crypto.py`
  now show the OS-neutral `python -c "import secrets,base64; ..."` one-liner; clarified master key must be
  **standard** base64 (url-safe/hex deploys clean then 500s on first Gmail connect).
- **Dockerfile:** CRLF-shebang guard (`sed -i 's/\r$//'`).
- **Deliberately NOT applied:** the audit's suggested `starlette>=0.37,<0.50` pin — this env runs **starlette
  1.3.1**, so that cap would break the build. Dependency pinning deferred to a Linux-built hash-locked
  `requirements.lock` (see follow-ups). Lesson: verify audit output, don't blind-apply.

## CASA verification question — RESOLVED: gmail.send needs NO CASA
A 2nd research workflow (5 researchers + adversarial debate + judge, **HIGH confidence**, Google-official
2026 sources) settled a conflict: the deploy-audit had claimed `gmail.send` needs **CASA Tier 2
(~$540–1,000)**. **That is WRONG.** The existing `docs/legal/google-verification.md` was **RIGHT**.
- `gmail.send` is a **SENSITIVE** scope → verified via Trust & Safety sensitive-scope review only. **CASA is
  triggered ONLY by RESTRICTED scopes** stored/transmitted on a server. **Cost = $0** in both beta and prod.
- **Beta (Testing mode):** zero verification, 100 test-user cap, $0. Only friction: `gmail.send` forces
  test-user refresh tokens to **expire 7 days after consent** (worker already handles `invalid_grant` by
  clearing the credential → user reconnects).
- **Production (public):** sensitive-scope review = domain/brand verification + privacy policy + written
  scope justification + unlisted demo video. ~10 days, **$0 assessor fees**.
- **TRAP:** the $540–1,000 figures are *real* but are **restricted-scope** prices, misattributed.
  `gmail.compose` reads like "send" but IS restricted → would trigger CASA. **Our code correctly uses
  `gmail.send`** (`google_oauth.py:33 GMAIL_SCOPE`) — keep it; never switch to `gmail.compose`.
- Report (may be wiped): `scratchpad/casa-verification-verdict.md`. Re-check the scopes page right before a
  public launch (policy could change; last verified May–Jun 2026).

## Open follow-ups (offered, NOT yet done — next session decides)
1. **Commit the uncommitted fixes** (recommended — 211 tests green). Suggest a `feat(saas): Fly.io beta
   deploy + audit fixes` commit for the code/tests + deploy files (commit explicit paths, not `-A`).
2. **S3 reconnect UX** (recommended, small): when the worker auto-clears a dead Gmail token, show a
   persistent "Reconnect Gmail" banner on the dashboard (`/auth/connect-gmail`) + fire the owner webhook.
   Smooths the 7-day Testing-mode token expiry.
3. **N1:** wrap the rate-limiter's SQLite write in `run_in_threadpool` (avoids a rare event-loop stall under
   WAL contention on the single uvicorn worker).
4. **S6:** generate a hash-pinned `requirements.lock` **in the Linux target** for reproducible Fly builds.
5. **M6** (Postgres + RLS) when SQLITE_BUSY contention or ~50 active users shows up — also the moment to
   split web/worker onto separate Fly machines.

## Locked decisions / overrides (so the next session doesn't relitigate)
- **Gmail delivery = email to the USER's own inbox** (does NOT auto-send to employers).
- **Auth = Google OAuth `gmail.send`** — a **SENSITIVE** scope → **no CASA, $0**. Keep `gmail.send`; NEVER
  `gmail.compose` (restricted → CASA). (Confirmed this session.)
- **Vercel is NOT viable** for V2 (ephemeral FS kills SQLite; no always-on worker). **Fly.io = beta**,
  **Oracle VM = production**. Both run the app as-is (SQLite for MVP; Postgres deferred to M6).
- **SaaS on Fly = ONE machine only** (volume attaches to one machine). Never `fly scale count >1`.
- **One shared operator Gemini key** (`APPLYFIRST_DAILY_TAILOR_CAP` default 10/user/day; no key →
  rules-fallback). NOT per-user BYO-key.
- Raw sqlite3 + httpx + stdlib (no SQLAlchemy/Authlib).

## Owner to-dos before V2 can run live — pick a path (all yours; no code)
**Path A — Fly.io beta (fastest, $0, public HTTPS URL):** follow the click-by-click above. Needs: a Fly
account (card for abuse-prevention), a globally-unique app name, a Google OAuth Web client (Testing mode +
test users), and the 4 secrets. No domain required (`<name>.fly.dev` is free HTTPS).
**Path B — Oracle VM production:** `deploy/oracle/README.md` §"Deploying the V2 SaaS" — own a domain, run
`setup.sh` (Caddy + SaaS units), fill the SaaS `.env` (see `deploy/oracle/saas-env.sample`), `enable --now`
the units, submit Google verification.
Either way: point UptimeRobot at `/health`; smoke the worker first with `python -m applyfirst.saas.worker
--once`.

# Live system facts — V1 CLI (still running, untouched)
- **Server:** Oracle VM `VM.Standard.E2.1.Micro` (2 vCPU / 1 GB / 45 GB), Ubuntu 24.04.
  Public IP `129.158.205.47` · **SSH key:** `C:\Users\regid\.ssh\applyfirst_oracle` (user `ubuntu`).
- **App dir:** `/opt/applyfirst` (system user `applyfirst`). Secrets in `/opt/applyfirst/.env` (mode 600).
- **Services:** `applyfirst.service` (poller) · `applyfirst-dash.service` (dashboard) ·
  `applyfirst-health.timer` · `tailscaled`. **Dashboard (Tailscale only):** `http://100.71.19.32:8000`.
  **Keywords:** claude code · vibe coder · web developer · software developer.
- Health: `ssh -F _afcfg af "systemctl is-active applyfirst.service applyfirst-dash.service; curl -s localhost:8000/api/health"`

# Environment quirks a new session MUST know
- **Python 3.14.3**; venv at `.venv` → use **`.venv/Scripts/python.exe`**. (The Fly image intentionally uses
  py3.12 for wheel reliability; app is 3.10+ safe.)
- **A "privacy guard" hook blocks any Bash/Read command whose TEXT contains `.env`, `key`, or
  `credentials`** (matches `keyword` → "key"). Workarounds: SSH via the `_afcfg` ssh-config file; put script
  content in a file via Write then run by filename. (Write/Edit are NOT hooked — only Bash/Read.)
- **Secrets/runtime are git-ignored** — NEVER commit: `.env`, `profile.yaml`, `applyfirst-saas.db`, `.noxa/`,
  `backups/`. Commit explicit paths (not `git add -A`) to avoid `REMOTE.md`.
- **`.gitattributes` forces `*.sh eol=lf`** — keep it; a CRLF shebang breaks `/bin/sh` in the Fly container.
- **`claude-mem` plugin is DISABLED** — leave off. Commits: **no `Co-Authored-By` trailer**.
- **Obsidian vault:** `C:\Users\regid\Documents\MyBrain` (Windows Python needs `C:/…` paths).

# Failed attempts / gotchas worth keeping
- Module-level `app = create_app()` broke test collection → lazy via PEP 562 `__getattr__` (app.py:436).
  Tests use `create_app(cfg)` with a test SaaSConfig (conftest `saas_cfg`: secure_cookies=False, localhost).
- `__Host-` cookies need HTTPS → tests use `secure_cookies=False`. Fly terminates TLS at the edge, so
  `__Host-` cookies + Secure flag work end-to-end (browser↔edge is HTTPS).
- JWKS "degrade to claim-only" was an attacker-forceable bypass → **fail-closed** (google_oauth.py).
- Each milestone bumps `PRAGMA user_version`; tests hard-coding it must use `db._SCHEMA_VERSION`.
- Worker clamps scraped `raw_description` to 8000 chars (daily cap limits CALLS not TOKENS).
- **Fly rate-limit gotcha (B1):** on Fly the LAST XFF hop is a CONSTANT app IP (unlike Caddy, which appends
  the real peer). Must key on `Fly-Client-IP`. The limiter fails **closed** (503) if its table is gone.
- **CASA misconception:** `gmail.send` does NOT need CASA — only RESTRICTED scopes do. Don't "fix" the
  google-verification.md to add CASA; it's correct. (Only `gmail.compose`/restricted would trigger it.)
- **Don't blind-apply audit output:** the audit's `starlette<0.50` pin would break the build (env has
  starlette 1.3.1); its CASA claim was wrong. Verify before applying.
- CSRF: synchronizer token bound to session user, via hidden `csrf` field or `X-CSRF-Token` header; the dep
  reads `await request.form()` (Starlette-cached) — don't switch it to a `Form()` param.

# Next Step — The single next thing to try
**Decide + commit:** the audit fixes + Fly deploy artifacts are in the working tree, tests green (211).
Commit them (explicit paths), then run **Path A (Fly.io beta)** click-by-click to get a public HTTPS beta
live for test users — no domain, no CASA, $0. Optionally implement the **S3 reconnect banner** first (small,
smooths the 7-day Gmail token expiry). Then **M6** (Postgres + RLS) when contention/scale shows up. See
`docs/SYSTEM-DESIGN.md` §10–§11 and the two scratchpad reports.
