# Run Agad on your own PC, end to end

The full walkthrough for testing the V2 SaaS on `localhost` with a real Google account, from an
empty Google Cloud project to an application landing in your own Gmail.

Everything here is localhost only. Deploying to a public address is a different runbook, see
`Handoff.md` and `deploy/oracle/README.md`.

Two windows stay open while you test. Window 1 is the website, window 2 is the worker that
watches onlinejobs.ph. Both must run from `C:\Users\regid\Desktop\applyfirst` so they share the
same `applyfirst-saas.db` file.

---

## Part A. Google Cloud setup

1. Go to https://console.cloud.google.com and sign in with your Gmail.
2. Top bar project picker, then **New project**, name it `agad`, **Create**, then select **agad**
   in the picker.
3. Top search bar, type `Gmail API`, click **Gmail API**, then **Enable**.
4. Top search bar, type `Google Auth Platform`, open it, then **Get started**.
5. App name **Agad**, User support email is your Gmail, then **Next**.
   This is the name Google shows your users on the permission screen, and the onboarding pages
   promise it says Agad, so it has to match.
6. Audience, **External**, then **Next**.
7. Contact information, your Gmail, then **Next**.
8. Tick the agreement box, **Continue**, then **Create**.
9. Left menu **Audience**, **Test users**, **Add users**, type your Gmail, then **Save**.
   While the app is in Testing only these addresses can sign in, up to 100 of them.
10. Left menu **Clients**, then **Create client**.
11. Application type **Web application**, Name `agad-local`.
12. Authorized redirect URIs, **Add URI**, `http://localhost:8000/auth/callback`
13. **Add URI** again, `http://localhost:8000/auth/gmail-callback`
14. **Create**, then copy the Client ID and Client secret into Notepad now.

## Part B. Make your encryption password

15. Open PowerShell and run this.

```powershell
cd C:\Users\regid\Desktop\applyfirst
.venv\Scripts\python.exe -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

16. Copy the line it prints into Notepad. **Always reuse this same one.** It encrypts the Gmail
    permission stored in the database, so a different one locks you out of everything already
    saved and you have to connect Gmail again.

## Part C. Start the website, PowerShell window 1

17. Replace the three PASTE values, then run it all.

```powershell
cd C:\Users\regid\Desktop\applyfirst
$env:APPLYFIRST_SAAS_SECURE_COOKIES = "false"
$env:APPLYFIRST_BASE_URL = "http://localhost:8000"
$env:GOOGLE_CLIENT_ID = "PASTE-CLIENT-ID"
$env:GOOGLE_CLIENT_SECRET = "PASTE-CLIENT-SECRET"
$env:APPLYFIRST_MASTER_KEY = "PASTE-ENCRYPTION-PASSWORD"
.venv\Scripts\python.exe -m uvicorn applyfirst.saas.app:app --port 8000
```

The setting names still start with `APPLYFIRST_`. Those are read by the machine, not by people,
so the rename to Agad deliberately left them alone. `SESSION_SECRET` is not needed here, because
with secure cookies switched off the app uses a development default.

## Part D. Click through the app

18. Open **http://localhost:8000/login** , not the homepage.
    The site is invite-only right now, so the homepage leads with "Ask for a beta invite" and
    keeps the Google button under "Already invited?". The login page puts it front and centre.
19. **Continue with Google**, then pick your Gmail.
20. If you see "Google hasn't verified this app", click **Advanced**, then
    **Go to Agad (unsafe)**. Google adds the word unsafe to every app it is still reviewing.
21. On **"Connect your Gmail"**, click **Connect Gmail**, then pick your Gmail.
    There is also a "Skip for now" link if you ever want to test that path.
22. Same unverified screen if it appears, then **tick "Send email on your behalf"** and
    **Continue**. Miss that tick and the app shows a calm amber note and asks you to try again,
    which is worth testing on purpose at least once.
23. On **"Your details"**, fill Your name, Job you're looking for, Your usual subject line and
    Your usual application message, then **Save and continue**.
24. On **"What jobs should we watch for?"**, type `web developer` into "Add a keyword", click
    **Add**, then **Next: see a sample**.
25. On **"Here's what we'll send you"**, click **Start watching for jobs**.
    This is where the switch-on animation plays.
26. You land on **"Watching onlinejobs.ph for you"**.

## Part E. Start the worker, PowerShell window 2

27. Same folder, same encryption password, so both windows share one database.

```powershell
cd C:\Users\regid\Desktop\applyfirst
$env:APPLYFIRST_SAAS_SECURE_COOKIES = "false"
$env:APPLYFIRST_BASE_URL = "http://localhost:8000"
$env:GOOGLE_CLIENT_ID = "PASTE-CLIENT-ID"
$env:GOOGLE_CLIENT_SECRET = "PASTE-CLIENT-SECRET"
$env:APPLYFIRST_MASTER_KEY = "PASTE-ENCRYPTION-PASSWORD"
$env:GEMINI_API_KEY = "PASTE-GEMINI-KEY"
.venv\Scripts\python.exe -m applyfirst.saas.worker --interval 300
```

28. Leave both windows open and watch your Gmail inbox.
29. To stop, press `Ctrl+C` in each window.

---

## Two things that will confuse you if nobody warns you

### The first cycle sends nothing, on purpose

The first time the worker sees a new keyword it only records what is already posted, so you are
not flooded with a backlog of old jobs. Only a job posted **after** that first cycle emails you.

So expect silence for the first five minutes. To test without waiting for a real new post, run a
single cycle at a time instead.

```powershell
.venv\Scripts\python.exe -m applyfirst.saas.worker --once
```

Run it once to lay the baseline, wait for onlinejobs.ph to get a new matching post, then run it
again.

### Without a Gemini key you still get an email, just not an AI one

The worker falls back to a plain rules letter when no AI key is set. Everything else works the
same. Set `GEMINI_API_KEY` as shown in step 27 to test the real AI letter, or delete that line if
you would rather skip it for now.

---

## If something goes wrong

| What you see | What it means | Fix |
|---|---|---|
| `redirect_uri_mismatch` on Google's page | The URI in the Google console does not match exactly | It must be `http`, not `https`, and port `8000`, and both URIs from steps 12 and 13 must be there |
| "Access blocked" or Google refuses your account | Your Gmail is not on the test-user list | Add it under Audience, Test users, step 9 |
| Amber note, "Google didn't give us permission to send" | You did not tick the send box | Tap Connect Gmail again and tick "Send email on your behalf" |
| The page says Google sign-in is not configured | The client ID is not set in that PowerShell window | The `$env:` lines only live in the window you typed them in, so set them again after reopening |
| The worker exits straight away | It could not read the encryption password | `APPLYFIRST_MASTER_KEY` is missing in window 2, and it must be the same value as window 1 |
| Nothing ever arrives in your inbox | Usually the baseline above, or two different databases | Check both windows are in `C:\Users\regid\Desktop\applyfirst` |
| Gmail stops working after about a week | Google forces a 7-day refresh-token expiry while an app is in Testing | Connect Gmail again from the dashboard. This goes away after Google verification |

---

## Keep your secrets out of git

The Client ID, the Client secret, the encryption password and the Gemini key belong in Notepad or
in a local `.env` file, never in a commit. `.env`, `applyfirst-saas.db`, `backups/` and `output/`
are all git-ignored already.
