# M5 — Polish + Launch

- **Date:** 2026-06-21
- **Milestone:** M5 (final MVP milestone before public beta). See `docs/SYSTEM-DESIGN.md` §10–§11.
- **Predecessors:** M1 auth (`8bde0f6`), M2 onboarding (`af04994`), M3 worker (`bd05688`), M4 verification readiness (`26342fb`).
- **Goal-when-done:** the SaaS is deployable to public HTTPS with two systemd units, the worker
  alerts the owner if it goes blind, abuse/brute-force on `/auth/*` is bounded, forms are
  CSRF-protected, the DB is backed up nightly, and the dashboard shows the user's daily usage.

---

## 1. Scope — the M5 deliverables

From SYSTEM-DESIGN §10 (M5 row) + the handoff "Next Step", split into **code/config we ship now**
and **owner-only infra** that the code is wired to consume.

| # | Deliverable | Status entering M5 | Ships in M5 |
|---|---|---|---|
| D1 | Caddyfile (HTTPS auto-LetsEncrypt reverse proxy) | missing | file w/ `{$APPLYFIRST_DOMAIN}` placeholder + setup.sh install |
| D2 | `applyfirst-saas-web.service` (uvicorn, 4 workers, bound 127.0.0.1) | missing | new unit |
| D3 | `applyfirst-saas-worker.service` (continuous jittered loop) | missing | new unit |
| D4 | Worker continuous-loop run mode | **exists** (`worker.py` loop) | jitter made two-sided; env tuned to 4–7 min |
| D5 | Dead-man's switch → **owner** alert | detection exists; delivery missing | new `notify.py` transport + debounced wiring |
| D6 | `/auth/*` rate limiting | missing | DB-backed fixed-window limiter |
| D7 | Nightly SQLite online-backup → gzip (+ optional remote) | core `backup_db` exists | `saas/backup.py` + timer; env-gated remote push |
| D8 | Daily-cap dashboard banner | missing | `get_ai_usage_today` + dashboard line |
| D9 | CSRF tokens on state-changing POSTs | SameSite=Lax only | synchronizer token on all 6 forms |
| D10 | Disconnect Gmail flow | **exists** (`/auth/disconnect-gmail`) | verify; add CSRF |
| D11 | `/health` endpoint (readiness) | `/healthz` liveness only | `/health` w/ db check + worker staleness |
| D12 | Config knobs for all the above | partial | new `SaaSConfig` fields, safe defaults |
| D13 | Deploy runbook for the SaaS units | missing | setup.sh + README section |

**Owner-only infra (code is wired and inert until these are supplied):** a **domain + DNS** (D1),
an **owner mailbox / SMTP creds OR a Slack/Discord webhook URL** (D5), and an **object-storage
bucket** for off-box backups (D7). None block shipping M5 code.

---

## 2. Design decisions

- **CSRF = stateless synchronizer token bound to the session user.** `sign(secret, {"csrf": uid})`
  reuses the existing HMAC `session.sign/unsign`. A `require_csrf` dependency reads the token from a
  hidden `csrf` form field **or** an `X-CSRF-Token` header (a custom header can't be set cross-origin
  without a CORS preflight we never grant, so either is a valid defense). It calls `await
  request.form()` (Starlette-cached, so the route's own `Form(...)` still parses) rather than
  injecting a `Form()` param — avoids an empty-body 422 on the no-field POST routes. Belt-and-braces
  on top of the existing SameSite=Lax cookies + CSP `form-action 'self'`.
- **Rate limit = DB-backed fixed window, not in-process.** With 4 uvicorn workers an in-process
  counter undercounts 4×. A `auth_rate_hits(bucket, hits, expires)` table keyed by `ip|window` and
  incremented with the same atomic `INSERT … ON CONFLICT … RETURNING` idiom as `try_increment_ai_usage`
  gives one shared, correct counter with no Redis (matches the SQLite-for-everything MVP decision).
  Client IP comes from `X-Forwarded-For` (Caddy is the only ingress) when `trust_proxy` is on.
- **Owner alert = pluggable, default-safe.** `notify.send_owner_alert(cfg, subject, body)` prefers a
  generic webhook (`{"text", "content"}` — works for Slack and Discord), then SMTP (reusing V1's
  `applyfirst.notify.email_smtp.SmtpNotifier`), then **log-only**. It never raises — a failed alert
  must never crash the worker. The worker has no send path of its own (`gmail_send` is tenant-bound),
  which is why this is a new transport. Debounced to ≤ once / 6 h via `worker_meta.last_owner_alert_at`.
- **Backup = local now, remote later.** `saas/backup.py` reuses `applyfirst.backup.backup_db` (online
  `.backup` → gzip → prune, WAL-safe, zero deps) against the **SaaS** DB. An env-gated
  `APPLYFIRST_BACKUP_REMOTE` shell template (with `{path}` substituted) pushes off-box when the owner
  configures rclone/aws/b2 — inert otherwise.
- **/health vs /healthz.** `/healthz` stays the dumb `"ok"` liveness (Caddy upstream check).
  `/health` is richer readiness: a trivial `SELECT 1` + worker staleness (`now - last_cycle_at` vs
  `2.5 × worker_interval`) → **503** when stale so UptimeRobot pages; a never-run worker is "starting"
  (200), so a fresh deploy doesn't page.
- **Schema → v4.** Only the rate-limit table is added; existing migrations untouched. Tests that
  hard-code the version use `db._SCHEMA_VERSION` (project convention).
- **The CLI (`applyfirst.db`) is untouched.** All M5 work is inside `applyfirst/saas/` + `deploy/oracle/`.

---

## 3. File-by-file changes

**Code (`applyfirst/saas/`)**
- `config.py` — +12 fields: owner-alert (`owner_alert_email`, `smtp_host/port/user/password`,
  `alert_webhook_url`), rate-limit (`auth_rate_limit`, `auth_rate_window`, `trust_proxy`), backup
  (`backup_dir`, `backup_keep`, `backup_remote_cmd`). All defaulted so old `.env` keeps loading.
- `db.py` — `_SCHEMA_VERSION = 4`; `_migrate_v4` creates `auth_rate_hits`; `record_auth_hit()`;
  `get_ai_usage_today()`.
- `session.py` — `issue_csrf()` / `verify_csrf()`.
- `notify.py` *(new)* — `send_owner_alert()`.
- `worker.py` — `_record_heartbeat(conn, result, cfg=None)` + `_maybe_alert_owner()` (debounced);
  two-sided jitter in the loop; `main()` passes `cfg`.
- `app.py` — `_rate_limit` middleware on `/auth/*`; `/health` route; `require_csrf` dependency on the
  6 POST routes; `csrf_token` + daily-cap `usage`/`cap` in authenticated template contexts.
- `backup.py` *(new)* — `run_backup(cfg)` + `main()`.
- `templates/` — hidden `csrf` inputs (base/logout, dashboard/disconnect, profile, keywords ×2,
  preview/activate); daily-cap banner in `dashboard.html`.

**Deploy (`deploy/oracle/`)**
- `applyfirst-saas-web.service`, `applyfirst-saas-worker.service`,
  `applyfirst-saas-backup.service` + `.timer`, `saas-backup.sh`, `Caddyfile` *(all new)*.
- `setup.sh` — install the new units/timer/Caddyfile; add the Caddy apt repo + package;
  `chmod +x` the backup script.
- `README.md` — a "Deploying the V2 SaaS" runbook section.

**Tests** — new: `test_saas_csrf.py`, `test_saas_rate_limit.py`, `test_saas_health.py`,
`test_saas_notify.py`, `test_saas_backup.py`, daily-cap banner assertions.
Updated: onboarding/connect-gmail/cross-tenant (set the CSRF header on the test client),
`test_saas_db_v3.py` (`== 3` → `db._SCHEMA_VERSION`), `test_saas_worker.py` (+owner-alert test).

---

## 4. Owner steps to actually launch (after this lands)

1. Fill the SaaS `.env` (mode 600): `GOOGLE_CLIENT_ID/SECRET`, `SESSION_SECRET`
   (`openssl rand -base64 32`), `APPLYFIRST_BASE_URL=https://<domain>`,
   `APPLYFIRST_SAAS_SECURE_COOKIES=1`, master key, optional `GEMINI_API_KEY`,
   worker tuning (`APPLYFIRST_WORKER_INTERVAL=330`, `APPLYFIRST_WORKER_JITTER=0.27`),
   and **one** owner-alert channel (`APPLYFIRST_ALERT_WEBHOOK` **or** the SMTP set + `APPLYFIRST_OWNER_EMAIL`).
2. Own a domain, point an A-record at the VM, open 80/443; set `APPLYFIRST_DOMAIN` for Caddy.
3. `sudo bash /opt/applyfirst/deploy/oracle/setup.sh`, drop the `.env`, then
   `systemctl enable --now applyfirst-saas-web applyfirst-saas-worker applyfirst-saas-backup.timer`
   and `systemctl reload caddy`.
4. Point UptimeRobot at `https://<domain>/health`.
5. Submit Google verification (runbook: `docs/legal/google-verification.md`).

---

## 5. Out of scope (deferred)

- **M6 Postgres + RLS** — triggered by sustained `SQLITE_BUSY` or ~50 active users.
- Off-box backup *provider* wiring (rclone/OCI/B2 config) — the hook ships; the bucket is owner infra.
- A separate alive-but-hung worker watchdog (the worker's `Restart=always` + the dead-man's-switch
  owner alert + `/health` 503 cover the operational gap; a self-restarting timer is a later add).
- Stripe billing, multi-résumé, sites beyond onlinejobs.ph (SYSTEM-DESIGN §12).
