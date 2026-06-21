# M4 — Google Verification Readiness — Plan

- **Owner:** Omhar (solo)
- **Design parent:** `docs/SYSTEM-DESIGN.md` §10 M4
- **Goal:** make ApplyFirst *submittable* for Google `gmail.send` verification — the live pages Google requires (public homepage describing Gmail usage, Privacy Policy, Terms) + footer privacy link + a ready-to-follow submission guide. The owner does the parts I can't: own/verify a domain, record the demo video, and click Submit in the console.

## Key research finding
**`gmail.send` is a SENSITIVE scope, not Restricted → no CASA (paid annual security audit) required.** Just Google's Trust & Safety review + scope justification + an unlisted demo video. Testing mode caps at 100 users and **expires refresh tokens every 7 days** (handled by the M3 worker's `invalid_grant` path → user reconnects; documented, no code change).

## Decisions (owner)
- Contact/support email: **omharregidor@gmail.com**
- Domain: not chosen → pages + guide use a clearly-marked `<YOUR_DOMAIN>` placeholder to swap in later.
- Waitlist: **not built** in M4.

## Done-when
- [ ] `/` serves a public homepage (anon) describing the app + why `gmail.send` is used, with a footer Privacy link, and "Continue with Google". Authed → `/dashboard`.
- [ ] `/privacy` and `/terms` are public (no auth), HTML, and **accurately** describe what the system does (verified against the code).
- [ ] Footer with Privacy + Terms links on every page (`base.html`).
- [ ] Privacy Policy includes the **Google API Services User Data Policy / Limited Use** affirmation (required for sensitive Gmail scopes) and discloses: data collected, `gmail.send` usage (send-to-self, no reading mail), Gemini processing, retention/deletion, no-sale/no-ads/no-AI-training.
- [ ] `docs/legal/google-verification.md`: scope tier, ordered checklist, ready-to-paste scope justification, demo-video script, 7-day-token note.
- [ ] Tests cover the public pages (200 without auth, key required content present); full suite still green.

## Out of scope (owner actions / later)
Owning + verifying a domain (Search Console DNS TXT), recording the demo video, the actual console submission, hosting/HTTPS (M5/deploy), the waitlist.

## File map
```
applyfirst/saas/
  app.py                       # MOD — public / homepage, /privacy, /terms routes
  templates/
    base.html                  # MOD — footer (Privacy · Terms · contact)
    home.html                  # NEW — public landing
    privacy.html               # NEW — Privacy Policy (ApplyFirst-specific)
    terms.html                 # NEW — Terms of Service
docs/legal/
  google-verification.md       # NEW — submission guide + scope justification + video script
tests/
  test_saas_legal.py           # NEW — public pages reachable + required content
```

## Steps
1. base.html footer + home/privacy/terms templates (accurate content; placeholders flagged).
2. app.py routes (`/` homepage, `/privacy`, `/terms` — all public).
3. Submission guide doc.
4. Tests + gate; Custodio fact-checks the privacy page against the implementation; commit.

## Changelog
- **2026-06-21** — v0.1. Built from a verification-requirements research pass (gmail.send = sensitive, no CASA). Pages + guide; owner does domain/video/submit.
