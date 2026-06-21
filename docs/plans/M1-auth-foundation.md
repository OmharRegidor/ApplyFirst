# M1 — Auth Foundation — Plan

- **Owner:** Omhar (solo)
- **Status:** 🟡 PLANNED — awaiting kickoff
- **Design parent:** [`docs/SYSTEM-DESIGN.md`](../SYSTEM-DESIGN.md) §10 M1, with the SQLite-MVP override active
- **Goal:** ship Google sign-in for the existing FastAPI + Jinja + htmx web app, with the schema seam + tenant isolation primitives that every later milestone (M2 onboarding, M3 worker, etc.) builds on. **No Gmail integration in M1.**

---

## 1. Done-when (acceptance criteria — hard gates)

A reviewer can verify each of these with a single command or click. M1 is **not** done until every box is green.

- [ ] `applyfirst-web` starts under HTTPS in dev (mkcert) **and** prod (Caddy + LetsEncrypt on the Oracle VM).
- [ ] Clicking **Continue with Google** completes the OAuth dance and lands the user on a protected `/me` page that shows their Google `display_name` + `email`.
- [ ] First sign-in INSERTs a row in `users` (`google_sub` UNIQUE); second sign-in for the same Google account UPSERTs the same row (no duplicates).
- [ ] Session cookie on prod is `__Host-applyfirst_session`, `HttpOnly`, `Secure`, `SameSite=Lax`; on dev `__Secure-applyfirst_session` (HTTPS still required).
- [ ] PKCE (`S256`), `state`, and `nonce` are all generated server-side, stored in the server-side session, and validated on `/auth/callback` BEFORE the code exchange. Mismatch returns 400 + invalidates session.
- [ ] `tenant_scope(session, user_id)` is the only sanctioned way to query `user_id`-scoped tables. Lint rule (`ruff` custom or `grep` CI step) fails the build on bare `session.execute(select(<TenantModel>))` outside the helper.
- [ ] Cross-tenant integration test passes: user A creates resource R; user B authenticates; `GET /api/resource/<R.id>` returns **404** (not 403). This test is in CI and blocks merge.
- [ ] All 41+ existing tests still pass.
- [ ] The existing single-user CLI (`python -m applyfirst.cli`) is **unchanged** and still works with its own `applyfirst.db` — the SaaS uses a separate DB file (`applyfirst-saas.db`).
- [ ] No secret material in logs (Google client secret, session secret, master key, code, state, nonce, access tokens). Verify with a one-time `grep -E '(client_secret|SESSION_SECRET|master)' <log file>` against captured prod logs.

---

## 2. Out of scope (deliberately deferred)

These belong to later milestones — do NOT start them in M1, even if they feel close:

| Deferred to | Item |
|---|---|
| M2 | "Connect Gmail" incremental authorization (`gmail.send` scope) |
| M2 | Refresh-token envelope encryption (write the schema columns in M1, leave them NULLable; the **encryption mechanics** land when we actually receive a refresh token in M2) |
| M2 | The 4-field onboarding wizard, keywords, preview, activation steps |
| M3 | Multi-tenant worker, shared poll, per-tenant fanout, tailoring cache, daily cap, Gmail API send |
| M4 | Privacy policy URL, ToS URL, Google verification application |
| M5 | Disconnect Gmail, daily-cap banner, "worker blind" alert, nightly SQLite backup to Object Storage, CSRF on htmx posts, `/auth/*` rate limit |
| M6 | Postgres migration + RLS |

---

## 3. Dependencies to add (`requirements.txt`)

| Package | Why | Notes |
|---|---|---|
| `sqlalchemy>=2.0` | Core (NOT ORM session magic) — dialect-swap seam for M6 | use the 2.0 `select()` / `connection.execute()` style |
| `alembic` | Schema migrations, dialect-neutral so M6 is a DSN swap | `alembic init` with `sqlalchemy.url` from env |
| `authlib` | Google OAuth client (PKCE, state, nonce, ID-token validation) | pure-Python; smaller than `requests-oauthlib` for our case |
| `itsdangerous` | Signed session cookie (URLSafeTimedSerializer) | already a transitive of Starlette; pin it explicit |

No new runtime deps beyond these four. No Redis, no Celery, no Docker, no nginx.

---

## 4. File map (what gets created / touched)

```
applyfirst/
  db/
    __init__.py
    engine.py          # SQLAlchemy 2.0 Engine factory, SQLite WAL pragmas
    models.py          # User, OAuthCredential — Core Table objects, NOT declarative ORM
    tenant.py          # tenant_scope(connection, user_id) — the ONLY sanctioned query helper
    crypto.py          # MasterKey loader (file → fallback env); AES-GCM helpers (unused in M1; needed for M2)
  auth/
    __init__.py
    google.py          # Authlib client config; PKCE/state/nonce generation + verify
    session.py         # itsdangerous-signed session middleware; __Host-/__Secure- cookie names
    routes.py          # /auth/login, /auth/callback, /auth/logout, /me
  web/
    app.py             # MODIFIED — register auth router, wire session middleware, gate existing dashboard behind require_user dependency
    templates/
      base.html        # MODIFIED — show display_name + logout in header when logged in
      login.html       # NEW — "Continue with Google" landing for unauthenticated visitors

alembic/
  env.py               # NEW — wired to applyfirst.db.engine
  versions/
    0001_users_oauth.py  # NEW — creates users + oauth_credentials

tests/
  test_auth_routes.py  # NEW — login URL is correct, callback validates state/nonce, session cookie set
  test_tenant_scope.py # NEW — bare select(TenantModel) raises; scoped query filters
  test_cross_tenant.py # NEW — user B requesting user A's resource returns 404

docs/plans/M1-auth-foundation.md  # this file
```

---

## 5. Plan steps (ordered — execute top-to-bottom)

Each step ends with a verification command. Mark the step done only after its verification passes.

### Step 1 — Dependencies + dev-HTTPS setup
- Add the four deps to `requirements.txt` and `requirements-dev.txt` (where appropriate).
- Run `.venv/Scripts/python -m pip install -r requirements-dev.txt`.
- Document mkcert-based local HTTPS in `docs/plans/dev-https.md` (one paragraph: `mkcert -install`, `mkcert localhost`, run uvicorn with `--ssl-keyfile localhost-key.pem --ssl-certfile localhost.pem`).
- **Verify:** `.venv/Scripts/python -c "import authlib, alembic, itsdangerous, sqlalchemy; print(sqlalchemy.__version__)"` prints 2.x.

### Step 2 — SQLAlchemy Engine + WAL pragmas
- Implement `applyfirst/db/engine.py`:
  - `make_engine(url: str) -> Engine` using `sqlalchemy.create_engine(url, future=True)`.
  - On SQLite URLs, attach a `connect` event that runs `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=10000` and `PRAGMA foreign_keys=ON`.
- Pick the DSN env var: `APPLYFIRST_SAAS_DSN`, default `sqlite:///applyfirst-saas.db`. This name (separate file) is what guarantees the CLI's `applyfirst.db` is untouched.
- **Verify:** a tiny `python -c "from applyfirst.db.engine import make_engine; e = make_engine('sqlite:///x.db'); print(e.dialect.name)"` prints `sqlite`.

### Step 3 — Models + Alembic baseline
- Implement `applyfirst/db/models.py` using SQLAlchemy 2.0 Core `Table` objects (not declarative):
  - `users(id TEXT PK, google_sub TEXT UNIQUE NOT NULL, email TEXT NOT NULL, display_name TEXT, plan TEXT NOT NULL DEFAULT 'free', created_at TEXT NOT NULL)` — IDs are UUID4 strings (str(uuid.uuid4())) for cross-dialect cleanliness.
  - `oauth_credentials(id TEXT PK, user_id TEXT FK→users.id ON DELETE CASCADE, provider TEXT NOT NULL DEFAULT 'google', refresh_token_ciphertext BLOB, refresh_token_iv BLOB, refresh_token_tag BLOB, encrypted_dek BLOB, gmail_scope_granted INTEGER NOT NULL DEFAULT 0, access_token_expiry TEXT, updated_at TEXT NOT NULL)` — encryption columns NULLable for M1.
  - Indexes: `users.google_sub` UNIQUE (auto), `oauth_credentials.user_id`.
- `alembic init alembic`, wire `env.py` to `applyfirst.db.engine.make_engine(os.environ["APPLYFIRST_SAAS_DSN"])`, generate `0001_users_oauth.py` (autogenerate from `metadata`).
- **Verify:** `alembic upgrade head` succeeds; `sqlite3 applyfirst-saas.db ".schema users"` shows the table.

### Step 4 — Master encryption key loader (scaffolded for M1, used by M2)
- Implement `applyfirst/db/crypto.py`:
  - `load_master_key() -> bytes`: read from `MASTER_KEY_PATH` env var if set (prod = `/etc/applyfirst/master.key`, mode 0600), else from `APPLYFIRST_MASTER_KEY` (base64) for local dev. Raise loudly if neither is present.
  - `encrypt_with_dek(plaintext, dek) -> (ciphertext, iv, tag)` and `decrypt_with_dek(...)`. Use the standard library's `secrets` for DEK generation and `cryptography` (already transitive) or `pycryptodome` for AES-GCM — pick `cryptography`; it's in the FastAPI stack already.
  - `encrypt_dek(dek, master) -> encrypted_dek` and `decrypt_dek(...)`.
- **Unused at runtime in M1** — but write the unit test now so M2 plugs in clean. Add `cryptography` to deps if it isn't already transitive.
- **Verify:** unit test round-trips a string through `(encrypt_with_dek + encrypt_dek)` → DB blob → `(decrypt_dek + decrypt_with_dek)` and gets the original back.

### Step 5 — Signed session middleware
- Implement `applyfirst/auth/session.py`:
  - Read `SESSION_SECRET` from env (32+ bytes, base64); refuse to start if missing in prod.
  - Use `itsdangerous.URLSafeTimedSerializer` with a 7-day max age.
  - Cookie name: `__Host-applyfirst_session` in prod (HTTPS-only, no Domain attr), `__Secure-applyfirst_session` in dev (HTTPS-only via mkcert).
  - Flags: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`.
  - Expose `request.session` like Starlette's built-in but with these guardrails.
- **Verify:** `pytest tests/test_session.py` round-trips a value through the cookie and rejects a tampered cookie.

### Step 6 — Google OAuth client (sign-in scopes only — `openid email profile`)
- Implement `applyfirst/auth/google.py` using Authlib's `StarletteOAuth2App`:
  - One OAuth client. Scopes: `openid email profile`. **NOT `gmail.send` — that's M2.**
  - Helper to start the flow: generate `state` (`secrets.token_hex(32)`), `nonce` (`secrets.token_hex(32)`), PKCE `code_verifier` (`secrets.token_urlsafe(96)`) → `code_challenge` (`S256`). All three stored in `request.session`.
  - Callback helper: read `code` + `state`; validate `state` against session; exchange code (with `code_verifier`); validate `id_token` audience + `nonce`; return parsed user identity dict `{google_sub, email, display_name}`.
- Configure the Google OAuth client in Google Cloud Console: redirect URIs = `https://localhost:8000/auth/callback` (dev) + `https://<your-prod-domain>/auth/callback`. Document this in `docs/plans/M1-auth-foundation.md` Appendix A (below).
- **Verify:** local sign-in works end-to-end against a real Google client; row appears in `users`.

### Step 7 — Routes
- Implement `applyfirst/auth/routes.py`:
  - `GET /auth/login` → 302 to Google authorize URL (per Step 6).
  - `GET /auth/callback` → validate, UPSERT user, set session, 302 to `/me`.
  - `POST /auth/logout` → clear session, 302 to `/login` (the landing page).
  - `GET /me` → JSON `{user_id, email, display_name, plan}` for the authenticated user, else 401.
- Add a `require_user(request) -> User` FastAPI dependency that 401s on no session.
- **Verify:** manual click-through in browser; `curl -i https://localhost:8000/me` without cookie returns 401.

### Step 8 — Tenant scope helper
- Implement `applyfirst/db/tenant.py`:
  - `class TenantScope` wraps a SQLAlchemy `Connection` and a `user_id`; exposes `select(table).where(table.c.user_id == self._user_id)` as the only entry point.
  - `@contextmanager def tenant_scope(engine, user_id): ...` yields a `TenantScope` over a Begin/Commit transaction.
  - Forbid bare `engine.execute(select(t))` against `TENANT_SCOPED_TABLES = {users, user_profiles, user_keywords, user_job_alerts, applications, ai_usage, oauth_credentials}` — add a runtime guard that imports the helper and checks the call site's frame for `_user_id` injection, OR (simpler) ship a `grep` step in CI: `grep -RnE "execute\(select\((User|OAuthCredential)" applyfirst/ | grep -v db/tenant.py && exit 1`.
- **Verify:** unit test `tests/test_tenant_scope.py` — calling `tenant_scope(engine, alice_id).select(users)` returns only alice's row; bare access via raw connection is caught by the grep step in CI.

### Step 9 — Cross-tenant integration test (the hard gate)
- Implement `tests/test_cross_tenant.py`:
  - Spin up the FastAPI app with a temp SQLite DB.
  - Create user A (Google sub `alice`) and user B (Google sub `bob`) via direct DB inserts.
  - Insert an OAuthCredential for A.
  - Authenticate as B (signed session cookie pointing to B).
  - `GET /api/oauth-credentials/<A's credential id>` → **assert status_code == 404** (not 403, not 401, not 200).
- This test runs in `pytest` and is part of the standard `pytest -q` run. CI is already green on `pytest -q`, so this slots in automatically.
- **Verify:** `pytest -q tests/test_cross_tenant.py` passes; deleting the `user_id` filter from the route makes it fail.

### Step 10 — Gate the existing dashboard
- Modify `applyfirst/web/app.py`:
  - Mount `applyfirst.auth.routes` at `/auth`.
  - Wire `applyfirst.auth.session.SessionMiddleware`.
  - Add a `require_user` dependency to the existing dashboard routes (currently the unauthenticated owner-private dashboard at `/`).
  - Edit `templates/base.html` to show `{{ user.display_name }}` + a logout button when authenticated.
  - Add `templates/login.html` (just a "Continue with Google" button and the disclaimer "we send tailored applications to YOUR inbox — you copy + paste").
- The owner becomes "user 0" by signing in once with their Google account.
- **Verify:** unauthenticated `GET /` redirects to `/login`; signed-in `GET /` shows the dashboard with the header username.

### Step 11 — Run the gauntlet
- `ruff check .` → clean.
- `pytest -q` → all green (existing 41 + new ~8 tests).
- Local manual sign-in → DB row appears → reload `/me` → JSON OK → logout → `/me` is 401.
- Cross-tenant test passes; mutating the route to drop the `user_id` filter makes it fail (proves the test bites).
- Commit per atomic-commits rule: one commit per Step that ends cleanly; e.g. `feat(db): SQLAlchemy Core + Alembic baseline (users, oauth_credentials)`.

---

## 6. Risks specific to M1

| # | Risk | Mitigation |
|---|---|---|
| R1 | **`__Host-` cookie requires HTTPS — local dev without HTTPS silently drops the session.** | Use `mkcert` for dev HTTPS (Step 1 doc); name the dev cookie `__Secure-applyfirst_session` (still HTTPS-required). Refuse to start the server over plain HTTP in any environment. |
| R2 | **OAuth redirect URI mismatch between dev and prod** (cause: forgot to register one of them in Google Cloud Console). | Appendix A below lists both required URIs; PR template asks for a screenshot of the Google Cloud Console URI list before merging M1. |
| R3 | **`tenant_scope()` not used by an engineer in a future PR → cross-tenant leak.** | The grep-based CI step in Step 8 + the integration test in Step 9. Both are blocking. |
| R4 | **Same `applyfirst.db` accidentally used by both CLI and SaaS → CLI's single-user data ends up in the SaaS user table.** | Different default DB filename (`applyfirst-saas.db`) + a startup assertion: if `APPLYFIRST_SAAS_DSN` ends with `applyfirst.db`, refuse to start. |
| R5 | **Authlib version drift can change PKCE defaults.** | Pin Authlib (`authlib==1.x.y`) and re-evaluate on every minor bump. |

---

## 7. Notes for Custodio (Security) — to verify at M1 sign-off

- PKCE `S256`, not `plain`.
- `state` and `nonce` both validated; `state` is single-use (deleted from session after callback).
- ID token `aud` validated against the Google client ID.
- Session secret in env, never logged.
- `__Host-` cookie in prod; `__Secure-` in dev; both have `HttpOnly`, `Secure`, `SameSite=Lax`.
- Cross-tenant test green in CI.
- No Gmail-related code, no refresh token handling — M2 territory.

---

## Appendix A — Google Cloud Console setup (one-time, owner does)

1. **Create a Google Cloud project** (or reuse one): https://console.cloud.google.com/
2. **OAuth consent screen** → User type = **External** → fill in app name `ApplyFirst`, user-support email, developer email. Scopes: leave empty for M1 (Google requests the minimal `openid email profile` set automatically; `gmail.send` is added in M2). Test users: add the owner's Gmail. Save.
3. **Credentials → Create credentials → OAuth client ID** → Application type = **Web application** → Name `applyfirst-web` → **Authorized redirect URIs**:
   - `https://localhost:8000/auth/callback` (dev)
   - `https://<your-prod-domain>/auth/callback` (prod — register before M5 launch)
4. Copy the **Client ID** + **Client Secret** into `.env`:
   ```env
   GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=...
   SESSION_SECRET=...      # 32 bytes base64; generate via `openssl rand -base64 32`
   APPLYFIRST_SAAS_DSN=sqlite:///applyfirst-saas.db
   APPLYFIRST_MASTER_KEY=...     # 32 bytes base64; generate via `openssl rand -base64 32` (dev only)
   ```
5. **Production master key** lives at `/etc/applyfirst/master.key` (`chmod 0600`, owned by the app user). Generate with `openssl rand -base64 32 > /etc/applyfirst/master.key && chmod 0600 /etc/applyfirst/master.key`.

---

## Appendix B — Atomic-commit shape

One commit per Step that ends green. Suggested subjects:

1. `chore(deps): add sqlalchemy 2.0, alembic, authlib, itsdangerous`
2. `feat(db): SQLAlchemy 2.0 engine factory with SQLite WAL pragmas`
3. `feat(db): users + oauth_credentials tables (Alembic 0001)`
4. `feat(crypto): master key loader + AES-GCM envelope encryption helpers (scaffolded for M2)`
5. `feat(auth): signed session middleware (__Host- / __Secure- cookie)`
6. `feat(auth): Google OAuth sign-in client (openid email profile, PKCE, state, nonce)`
7. `feat(auth): /auth/login, /auth/callback, /auth/logout, /me routes`
8. `feat(db): tenant_scope helper + CI grep step banning bare tenant queries`
9. `test(security): cross-tenant access returns 404 (not 403)`
10. `feat(web): gate dashboard behind sign-in; add login page`

---

## Changelog

- **2026-06-21** — v0.1 of M1 plan. Authored by Bryl, scoped strictly to Auth foundation per the SQLite-MVP override in SYSTEM-DESIGN.md v0.2. No Gmail / no onboarding wizard / no worker in M1.
