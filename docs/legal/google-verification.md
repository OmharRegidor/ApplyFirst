# Google OAuth Verification — Submission Guide (gmail.send)

Owner runbook for getting ApplyFirst verified for the `gmail.send` scope. Built from a
2026 research pass against Google's official docs.

> **First, a caveat on the legal pages.** The Privacy Policy (`/privacy`) and Terms
> (`/terms`) shipped in M4 are accurate to what ApplyFirst does, but they are **templates,
> not legal advice** — read them and adapt (entity name, jurisdiction, any extra data you
> later collect) before relying on them publicly.

## The big finding: `gmail.send` is a SENSITIVE scope (not Restricted)

→ **No CASA security assessment** (the paid, annual third-party audit) is required. CASA is
only triggered by *Restricted* Gmail scopes (`gmail.readonly`, `gmail.modify`, `mail.google.com/`,
etc.). Sensitive-scope verification = Google's own Trust & Safety review + a scope
justification + an unlisted demo video. This keeps M4 cheap and self-serviceable.

Source: Google "Choose Gmail API scopes" + "Sensitive scope verification".

## What ApplyFirst already provides (built in M4)

| Google requirement | Where |
|---|---|
| Public homepage describing the app + Gmail usage, with a footer privacy link | `GET /` → `home.html` (footer in `base.html`) |
| Privacy Policy (public, no login, HTML, Limited Use affirmation) | `GET /privacy` → `privacy.html` |
| Terms of Service (recommended) | `GET /terms` → `terms.html` |
| Requests only `gmail.send` (no broader scope) | `applyfirst/saas/google_oauth.py` `GMAIL_SCOPE` |
| Redirect URIs | `/auth/callback` (sign-in), `/auth/gmail-callback` (Gmail) |

Once hosted on your domain, the URLs Google needs are:
`https://<YOUR_DOMAIN>/`, `https://<YOUR_DOMAIN>/privacy`, `https://<YOUR_DOMAIN>/terms`.

## One-time setup (owner)

1. **Register a domain** you own (not GitHub Pages / Notion / Google Sites — Google must be
   able to verify ownership).
2. **Deploy ApplyFirst on it over HTTPS** (M5/deploy) so `/`, `/privacy`, `/terms` are
   publicly reachable with no login.
3. **Verify the domain in Google Search Console** as a **Domain property** (DNS TXT record),
   using the same Google account that is a **Project Owner** on your GCP project.

## OAuth consent screen (Cloud Console → APIs & Services → OAuth consent screen)

- User type: **External**
- App name: **ApplyFirst** (must match the homepage branding exactly)
- App logo
- Support email: **omharregidor@gmail.com**
- Authorized domain: `<YOUR_DOMAIN>` (must match the Search Console verified domain)
- Homepage URI: `https://<YOUR_DOMAIN>/`
- Privacy policy URI: `https://<YOUR_DOMAIN>/privacy`
- Terms of service URI: `https://<YOUR_DOMAIN>/terms`
- Scopes: add **only** `https://www.googleapis.com/auth/gmail.send` (plus the basic
  `openid email profile` sign-in scopes).

## Submission

1. Record an **unlisted YouTube** demo video (English, < 5 min) that shows:
   - the OAuth consent flow with **"ApplyFirst"** visible on the consent screen,
   - the browser **address bar showing your OAuth client ID** (Google asks for this),
   - the app **actually using the scope** — i.e. ApplyFirst sending a tailored application
     email to the user's inbox.
2. Paste the **scope justification** (below).
3. Click **Submit for verification**, provide the contact email, and respond promptly to any
   Trust & Safety follow-ups. Typical timeline: brand verification ~2–3 business days; sensitive
   scope review up to ~10 business days (longer if there's back-and-forth).

### Ready-to-paste scope justification — `gmail.send`

> ApplyFirst is a job-application assistant for onlinejobs.ph job seekers. When a new job
> matching the user's saved keywords is posted, ApplyFirst generates a tailored application and
> needs to deliver it to the user so they can review and send it. We use `gmail.send` to email
> that ready-to-paste application **from and to the user's own Gmail account** — i.e. to the
> user's own inbox — so it is waiting for them when they apply. We send only to the
> authenticated user's own address; we never email employers or third parties on their behalf.
> A narrower scope is not sufficient because there is no Gmail scope below `gmail.send` that
> permits sending mail. We do not request, and do not need, any read, modify, or metadata Gmail
> scope: ApplyFirst never reads, lists, or alters the user's existing mail. The OAuth refresh
> token is stored encrypted at rest (AES-256 envelope encryption) and used solely for this
> send. This is described to users on our homepage and Privacy Policy, which include the
> required Google API Services User Data Policy Limited Use affirmation.

## Testing-mode caveats (before verification clears)

- **Max 100 test users.** Add testers' Google emails to the consent screen's test-user list;
  others can't complete OAuth until you're verified/published.
- **"Unverified app" warning.** Test users see a "Google hasn't verified this app" interstitial
  and must click **Advanced → Go to ApplyFirst (unsafe)** to proceed. Expected until verified.
- **7-day refresh-token expiry.** In testing mode, `gmail.send` refresh tokens expire 7 days
  after consent. ApplyFirst already handles this: the worker treats `invalid_grant` as
  "reconnect needed" — it clears the stored credential and the user re-connects Gmail. This
  weekly reconnect goes away once the app is verified and in Production. (No code change needed;
  see `applyfirst/saas/gmail_send.py` + `worker.process_alert`.)

## Common rejection reasons (avoid these)

1. Vague scope justification (the #1 cause — the text above is specific on purpose).
2. Privacy policy hosted on a domain you don't own.
3. Homepage not publicly accessible, or doesn't mention Google-data usage.
4. Missing footer privacy link on the homepage (we ship one in `base.html`).
5. Demo video missing the address-bar client ID or actual scope usage, or not in English.
6. App name on the consent screen not matching the homepage.

Sources: developers.google.com (sensitive-scope verification, Gmail API scopes), support.google.com
(app homepage, domain verification, privacy policy, manage app audience).
