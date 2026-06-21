# M2 — Onboarding Wizard + Connect Gmail — Plan

- **Owner:** Omhar (solo)
- **Status:** 🟡 PLANNED — awaiting checkpoint
- **Design parent:** [`docs/SYSTEM-DESIGN.md`](../SYSTEM-DESIGN.md) §5 (onboarding flow), §6 (Connect-Gmail sequence), §10 M2
- **Builds on:** M1 auth foundation (`applyfirst/saas/`, commit 8bde0f6)
- **Goal:** a signed-in user completes a <3-minute onboarding — connect Gmail, fill the 4-field profile, add keywords, preview a sample application — and lands "activated." Their `gmail.send` refresh token is stored **envelope-encrypted**. NO polling and NO real email sending yet (that is M3).

---

## 1. Done-when (acceptance criteria)

- [ ] A fresh signed-in user is routed through the wizard and cannot reach `/dashboard` as "activated" until every required step is done.
- [ ] **Connect Gmail** runs Google **incremental authorization** for `gmail.send` (separate from M1 sign-in), and on success stores a refresh token that is **AES-256-GCM envelope-encrypted** (per-row DEK, DEK encrypted by the master key). The raw token is never written to the DB.
- [ ] **Disconnect Gmail** calls Google's `/revoke` endpoint and zeroes the encrypted columns.
- [ ] The **4-field profile** (Name, Type of Job, Standard Subject, Standard Message) persists to `user_profiles`; Name is pre-filled from the Google display name; editing recomputes `profile_hash`.
- [ ] **Keywords**: a user can add (≥1 required) and remove search keywords; they persist to `user_keywords`.
- [ ] **Preview**: the user sees a sample ready-to-paste application built from their profile against a fixture job, with explicit "we send this to YOUR inbox; you copy + paste" framing.
- [ ] **Activate** marks onboarding complete; the dashboard then shows an activated state.
- [ ] **JWKS hardening (Custodio M1 P2-3):** the sign-in `id_token` RSA signature is now verified against Google's JWKS (feasible now that `cryptography` is a dep).
- [ ] All existing tests still pass; new tests cover crypto round-trip, the v2 migration, the onboarding state machine, the connect-Gmail flow (mocked), and the preview.
- [ ] The single-user CLI and `applyfirst.db` remain untouched.

---

## 2. Out of scope (deferred)

| Deferred to | Item |
|---|---|
| M3 | The polling worker, per-tenant fanout, **actually sending** the tailored email via the Gmail API, the daily cap, tailoring cache |
| M3 | Wiring the live Gemini provider into the preview (M2 preview uses the deterministic rules-fallback — the user's Standard Message against a fixture job — so onboarding costs nothing and needs no API key) |
| M4 | Google app verification submission |
| M5 | Daily-cap banner, "worker blind" alert, nightly backup, `/auth/*` rate limit |
| M6 | Postgres + RLS |

---

## 3. Dependencies

| Package | Why |
|---|---|
| `cryptography>=43` | AES-256-GCM envelope encryption + JWKS RSA id_token verification. Installs on Py3.14 via the `cp311-abi3` wheel (verified). |

(Add to `requirements.txt`. Still no SQLAlchemy/Alembic/Authlib — same stdlib+httpx posture as M1.)

---

## 4. File map

```
applyfirst/saas/
  crypto.py        # NEW — master-key loader + AES-GCM envelope encrypt/decrypt
  db.py            # MOD — migration v2: user_profiles, user_keywords; profile/keyword/gmail-token fns
  google_oauth.py  # MOD — connect-Gmail incremental auth URL, gmail token exchange, JWKS verify, revoke
  onboarding.py    # NEW — onboarding state machine (next required step from data presence)
  preview.py       # NEW — build a Profile from the 4 fields → TailoringEngine (fallback) → sample package
  app.py           # MOD — onboarding routes + connect/disconnect Gmail routes; gate dashboard on completion
  templates/
    onboarding_connect_gmail.html  # NEW
    onboarding_profile.html        # NEW
    onboarding_keywords.html       # NEW
    onboarding_preview.html        # NEW
    dashboard.html                 # MOD — activated vs needs-onboarding state

tests/
  test_saas_crypto.py        # NEW — envelope round-trip, tamper, wrong master key, missing key
  test_saas_db_v2.py         # NEW — v2 migration, profile upsert + hash, keyword CRUD, encrypted token store/get
  test_saas_onboarding.py    # NEW — state machine + wizard routes + gating
  test_saas_connect_gmail.py # NEW — incremental auth URL, gmail callback stores encrypted token, disconnect revokes
  test_saas_preview.py       # NEW — preview builds from 4 fields, no API key needed
```

---

## 5. Plan steps (ordered)

1. **Deps + crypto module.** Add `cryptography` to `requirements.txt`. Implement `crypto.py`: `load_master_key()` (`MASTER_KEY_PATH` file in prod / `APPLYFIRST_MASTER_KEY` base64 in dev, fail loudly if neither), `encrypt_secret(plaintext) -> EnvelopeBlob{ciphertext, iv, encrypted_dek}` (per-row DEK via `AESGCM.generate_key`, DEK encrypted by master key; GCM tag rides inside ciphertext), `decrypt_secret(blob) -> bytes`. **Verify:** unit round-trip + tamper + wrong-key tests.
2. **DB migration v2.** Add `user_profiles` and `user_keywords` tables; bump `user_version` to 2 via `_migrate_v2`. Add fns: `upsert_profile`, `get_profile`, `add_keyword`, `list_keywords`, `delete_keyword`, `store_gmail_credential` (encrypt + write the M1 columns + set `gmail_scope_granted=1`), `get_gmail_refresh_token` (decrypt, tenant-scoped), `clear_gmail_credential`. **Verify:** v2 migration idempotent + from-v1 upgrade; profile hash changes on edit; FK + tenant scope hold.
3. **Google OAuth additions.** `build_connect_gmail_url` (scope `gmail.send`, `access_type=offline`, `prompt=consent`, `include_granted_scopes=true`); `exchange_code_for_gmail` (returns refresh_token); `verify_id_token_signature` (fetch + cache Google JWKS, verify RS256) wired into the M1 sign-in `fetch_identity`; `revoke_token`. **Verify:** URL params; mocked exchange; JWKS verify accepts a correctly-signed token and rejects a tampered one.
4. **Onboarding state machine.** `onboarding.py`: `next_step(user, conn) -> 'connect_gmail'|'profile'|'keywords'|'preview'|'done'` from data presence (gmail connected? profile rows? ≥1 keyword? activated flag?). Store an `onboarding_completed_at` on `user_profiles` (or a `users` column) set by Activate. **Verify:** each missing-data state routes to the right step.
5. **Routes + templates.** `/onboarding` (redirect to next step), `/onboarding/profile` (GET form + POST save), `/onboarding/keywords` (GET + POST add / POST delete), `/onboarding/preview` (GET render sample), `/onboarding/activate` (POST), `/auth/connect-gmail` + `/auth/gmail-callback`, `/auth/disconnect-gmail`. All behind `require_user`; CSRF-safe (state-changing = POST). Dashboard shows activated vs "finish setup." **Verify:** full wizard walk via TestClient ends activated.
6. **Preview.** `preview.py`: map the 4 fields → `applyfirst.profile.Profile` (full_name, target_summary=job_type, base_pitch=standard_message, subject_library={'general':[standard_subject]}), run `TailoringEngine(provider=None)` against a bundled fixture job, return the package. **Verify:** returns a cover letter containing the user's Standard Message, no network/key.
7. **Gauntlet.** `py_compile` + full `pytest`; manual wizard walk; verify-and-fix wave (Custodio security + Franco QA), fix, re-gate.

---

## 6. Risks specific to M2

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Master key mishandling** — lose it and every stored token is unrecoverable; leak it and every token is exposed | `load_master_key()` fails loudly if absent; prod key in a 0600 file outside the DB & repo; document backup. Never log it. |
| R2 | **Refresh token only returned on first consent** — Google omits `refresh_token` on re-consent without `prompt=consent` | always set `prompt=consent` + `access_type=offline` on the connect-Gmail URL; if no refresh_token comes back, surface a clear "please re-grant" error, don't store a half-credential |
| R3 | **Partial onboarding leaves dangling state** | state machine derives the next step from data presence (idempotent); no separate brittle step counter |
| R4 | **JWKS fetch failure breaks sign-in** | cache JWKS in-memory with TTL; on fetch failure fall back to the M1 claim-only validation (degrade, don't lock everyone out) — logged |
| R5 | **CSRF on the new POST forms** | all state-changing routes are POST behind the session cookie (SameSite=Lax); add the synchronizer-token follow-up in M5 as planned |

---

## 7. Notes for Custodio (verify at sign-off)
Envelope encryption (per-row DEK, master key never in DB), raw token never stored/logged, revoke on disconnect, incremental `gmail.send` (not combined with sign-in), JWKS RS256 verification added, tenant-scoped token reads, POST-only mutations.

## Changelog
- **2026-06-21** — v0.1 M2 plan by Bryl. `cryptography` confirmed installable on Py3.14 (abi3), so envelope encryption + JWKS verification are in-scope (no longer deferred). Email sending + polling remain M3.
