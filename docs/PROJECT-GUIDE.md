# Agad project guide

Written on 27 September 2026 for the owner. It explains every part of Agad in plain words.

- Every claim about the code comes from the files on disk today, including the alert-rule fix that is not committed yet. Each one carries a `path:line` link. Click it to open the file on that line.
- Every outside fact carries a link to where it came from. Anything nobody could confirm on an official page is marked **UNVERIFIED**.
- Words that may be new are explained where they first appear, and again in the [glossary](#13-glossary).

## Contents

1. [Agad on one page](#1-agad-on-one-page)
2. [The big picture](#2-the-big-picture)
3. [Where it runs](#3-where-it-runs)
4. [What happens when a user signs up](#4-what-happens-when-a-user-signs-up)
5. [The engine that finds jobs and sends applications](#5-the-engine-that-finds-jobs-and-sends-applications)
6. [Data and safety](#6-data-and-safety)
7. [Keeping it healthy](#7-keeping-it-healthy)
8. [The code base tour](#8-the-code-base-tour)
9. [What to expect](#9-what-to-expect)
10. [Scaling when traffic grows](#10-scaling-when-traffic-grows)
11. [Getting paid](#11-getting-paid)
12. [The MVP and the launch checklist](#12-the-mvp-and-the-launch-checklist)
13. [Glossary](#13-glossary)
14. [Sources](#14-sources)

---

## 1. Agad on one page

**In short.** Agad watches onlinejobs.ph for a job seeker and, minutes after a matching job is posted, puts a ready-to-paste application in their own Gmail so they can apply first. It is built and tested, it has worked end to end on your PC with a real Google account, and it has never run on the internet.

### What it does for a user

1. They sign in with Google.
2. They connect Gmail. That gives Agad permission to send email as them, and only ever to them.
3. They fill in four things. Their name, the kind of job they want, their usual subject line and their usual application message.
4. They add up to 20 watch words, like "shopify" or "virtual assistant" ([`applyfirst/saas/app.py:68-69`](../applyfirst/saas/app.py#L68-L69)).
5. They press Start. From then on, about every 10 minutes, Agad searches onlinejobs.ph for their words. When a new matching job appears, Gemini (Google's AI) tailors their own message to that job, and the result lands in their inbox. They read it, paste it into onlinejobs.ph and apply.

Agad never applies for anyone and never logs in to onlinejobs.ph. The email is sent from the user to the same user ([`applyfirst/saas/gmail_send.py:72-81`](../applyfirst/saas/gmail_send.py#L72-L81)).

### The promise

The homepage headline is "New job posted. Apply Agad." ([`applyfirst/saas/templates/home.html:31`](../applyfirst/saas/templates/home.html#L31)). "Agad" is Tagalog for "right away". The line under it promises a ready-to-paste application in your own Gmail within minutes ([`applyfirst/saas/templates/home.html:32`](../applyfirst/saas/templates/home.html#L32)). The pages offer a 14-day free trial and keep the price hidden for now, with "₱199 a month" ready to switch on ([`applyfirst/saas/templates/_ui.html:15-20`](../applyfirst/saas/templates/_ui.html#L15-L20)).

### Two surfaces, V1 and V2

| | V1, the personal tool | V2, the public service |
|---|---|---|
| Who uses it | You only | Any onlinejobs.ph applicant |
| Where the code lives | `applyfirst/` (`cli.py`, `pipeline.py`) | `applyfirst/saas/` |
| Its database file | `applyfirst.db` | `applyfirst-saas.db` |
| How letters arrive | Your own mail account by SMTP | Each user's own Gmail, through Google's Gmail API |
| Running today | Yes, on the Oracle server (per the handoff notes) | No, only on your PC |

The two never share a database file. V2 borrows V1's job reader, letter writer, email layout, backup code and mail sender (section 8.2).

### Where things stand today

- **Built.** Sign-in, the four sign-up steps, the dashboard, the worker, AI letters, Gmail sending, reconnect emails, owner alerts, backups and health checks are all in the code. Milestones M1 to M5 and the launch-blocker fixes B1 to B6 are committed and pushed.
- **Tested.** 1,391 automated tests pass. The smoke script, a quick check that opens every page and submits every form, passes all 607 of its checks. Both were measured on 27 September 2026 on the working copy (section 8.4).
- **Tried for real.** On 26 September 2026 you ran the real app on your PC with a real Google account. Sign-in and Connect Gmail worked and the first real application emails arrived.
- **One fix waits to be committed.** That first real run queued 59 alerts for one new user in a single round, mostly old jobs ([`docs/SYSTEM-DESIGN.md:350-353`](../docs/SYSTEM-DESIGN.md#L350-L353)). The alert rule now sends a user only jobs first stored after they started watching for them ([`applyfirst/saas/db.py:636-665`](../applyfirst/saas/db.py#L636-L665)). It is on disk and tested, but not committed (section 5.4).
- **Not deployed.** There is no Fly app yet. V2 has never run outside your PC.
- **Do before any deploy.** Make a new Google client secret, the password Agad uses to talk to Google, and delete the old one, because the old one appeared in a screenshot during setup.

### What stands between today and paying users

1. Written permission from onlinejobs.ph, and a slower, more honest crawler, meaning the part that reads their site (section 9.1).
2. Google's verification of the Gmail sending permission (section 9.2).
3. Gemini on the paid tier, with its thinking, the hidden reasoning it is billed for, turned down (section 9.3).
4. A way to take money (section 11).
5. Account deletion, updated legal pages and a registered business (section 12).

---

## 2. The big picture

**In short.** Agad is two programs on one server that share one database file. The web app talks to people, the worker talks to the outside world, and the two never call each other. They leave notes for each other in the database, like two people on different shifts sharing one notebook.

```mermaid
flowchart LR
  subgraph People
    B["Browser<br/>the job seeker"]
    Inbox["The user's own Gmail inbox"]
    Owner["You, the owner"]
    UR["Uptime monitor<br/>e.g. UptimeRobot"]
  end

  subgraph Server["One server (Fly machine or Oracle VM)"]
    Web["Web app<br/>applyfirst/saas/app.py"]
    Worker["Worker<br/>applyfirst/saas/worker.py<br/>one round about every 10 min"]
    DB[("SQLite file<br/>applyfirst-saas.db")]
    Bk[("backups folder<br/>last 7 daily copies")]
  end

  subgraph Outside["Outside services"]
    GAuth["Google sign-in"]
    GMail["Gmail API<br/>gmail.send"]
    Gem["Gemini AI"]
    OJ["onlinejobs.ph<br/>public job pages"]
    SMTP["Mail server (SMTP)<br/>the server's own account"]
    Hook["Webhook<br/>Slack or Discord"]
  end

  B -->|"pages and forms"| Web
  Web -->|"sends the browser to Google"| GAuth
  GAuth -->|"back to the two callback pages"| Web
  Web <-->|"read and write"| DB
  Worker <-->|"read and write"| DB
  Worker -->|"search each watch word"| OJ
  Worker -->|"write one letter for one user"| Gem
  Worker -->|"send as the user, to the user"| GMail
  GMail --> Inbox
  Worker -->|"your Gmail connection ended"| SMTP
  SMTP --> Inbox
  Worker -->|"owner alerts"| Hook
  Worker -.->|"owner alerts if no webhook"| SMTP
  Hook --> Owner
  Worker -->|"daily copy"| Bk
  UR -->|"GET /health"| Web
```

**How to read it.** The browser only ever talks to the web app. Only the worker reaches onlinejobs.ph, Gemini and the Gmail API. The database in the middle is how the two halves hear about each other. The dotted line is a spare route used only when no webhook is set.

### What each box is

- **Browser.** The job seeker's phone or computer. It gets pages, style files and signed cookies, which are small notes the browser keeps, sealed so nobody can change them. It may load nothing from any other site ([`applyfirst/saas/app.py:229-232`](../applyfirst/saas/app.py#L229-L232)).
- **Web app.** The program that answers every page and form. It is built with FastAPI, a Python toolkit for websites, and run by uvicorn, the program that listens for browsers. One function, `create_app`, assembles it ([`applyfirst/saas/app.py:210`](../applyfirst/saas/app.py#L210)).
- **Worker.** A second program with no pages that wakes up, does one round of work and sleeps, forever ([`applyfirst/saas/worker.py:613-620`](../applyfirst/saas/worker.py#L613-L620)).
- **SQLite file.** The one database, a single file both programs open the same way ([`applyfirst/saas/db.py:103-110`](../applyfirst/saas/db.py#L103-L110)).
- **Backups folder.** Dated, compressed copies of that file, the newest 7 kept ([`applyfirst/backup.py:107-113`](../applyfirst/backup.py#L107-L113)).
- **Google sign-in.** Where the browser goes to prove who the person is ([`applyfirst/saas/google_oauth.py:73-86`](../applyfirst/saas/google_oauth.py#L73-L86)).
- **Gmail API.** Google's door for sending an email as the user ([`applyfirst/saas/gmail_send.py:84-100`](../applyfirst/saas/gmail_send.py#L84-L100)).
- **Gemini.** Google's AI, which tailors each letter. The only call to it is one line ([`applyfirst/tailor/llm.py:41`](../applyfirst/tailor/llm.py#L41)).
- **onlinejobs.ph.** The job site. Agad reads its public search and job pages ([`applyfirst/sources/onlinejobsph.py:54-66`](../applyfirst/sources/onlinejobsph.py#L54-L66)).
- **Mail server (SMTP).** The server's own email account. It tells users their Gmail connection ended ([`applyfirst/saas/reconnect.py:223-249`](../applyfirst/saas/reconnect.py#L223-L249)) and carries owner alerts when no webhook is set ([`applyfirst/saas/notify.py:49-56`](../applyfirst/saas/notify.py#L49-L56)).
- **Webhook.** A secret web address that turns a message into a Slack or Discord post, the first choice for owner alerts ([`applyfirst/saas/notify.py:31-47`](../applyfirst/saas/notify.py#L31-L47)).
- **Uptime monitor.** An outside service that calls `/health` every few minutes and wakes you when it answers 503, the web code for "not healthy" ([`applyfirst/saas/app.py:459-515`](../applyfirst/saas/app.py#L459-L515)).
- **The user's inbox.** Where the finished application lands.
- **You.** You get alerts, never user letters.

The shared notebook is a small table called `worker_meta`. The worker writes the time of its last round and how many blind rounds it had in a row ([`applyfirst/saas/worker.py:402-408`](../applyfirst/saas/worker.py#L402-L408)). A blind round is one where onlinejobs.ph gave back nothing (section 7.4). It also writes whether the AI is on ([`applyfirst/saas/worker.py:453-454`](../applyfirst/saas/worker.py#L453-L454)). The web app's `/health` page reads all three ([`applyfirst/saas/app.py:476-478`](../applyfirst/saas/app.py#L476-L478)).

The worker's heartbeat is this loop.

```python
# applyfirst/saas/worker.py:613-620
while True:
    try:
        _cycle(conn, source, cfg, master_key, dog)
    except Exception as exc:
        log.event(_LOG, "worker_cycle_crashed", level=logging.ERROR, error=str(exc)[:200])
    # Two-sided jitter (±worker_jitter fraction) so the cadence centers on `interval`.
    delay = interval + random.uniform(-1.0, 1.0) * interval * cfg.worker_jitter
    time.sleep(max(1.0, delay))
```

**Plain reading.** `while True` means "repeat forever". One round, then a nap of about 10 minutes that wobbles a little each time, so the visits to onlinejobs.ph never look robotic. When you read any background program, find its forever loop first. Everything else hangs off it.

---

## 3. Where it runs

**In short.** All of V2 runs on one small computer. For the beta that is one Fly.io machine in Singapore, and for later there is a ready runbook for the Oracle server that already runs V1.

### 3.1 What runs inside the one machine

- **The web app**, started by uvicorn on port 8080 on Fly. A port is a numbered door on the machine that one program listens at ([`entrypoint.sh:46`](../entrypoint.sh#L46)).
- **The worker**, started in a restart loop beside it ([`entrypoint.sh:30-43`](../entrypoint.sh#L30-L43)).
- **The database file** `applyfirst-saas.db`, on a disk that survives restarts, called a volume ([`fly.toml:36`](../fly.toml#L36), [`fly.toml:52-54`](../fly.toml#L52-L54)).
- **The backups folder** on the same volume ([`fly.toml:37`](../fly.toml#L37)).

Why one machine. A Fly volume plugs into one machine only, and both programs need the same database file. So the app must never be scaled to two machines ([`fly.toml:3-5`](../fly.toml#L3-L5), [`entrypoint.sh:8`](../entrypoint.sh#L8)). A second machine would get its own empty volume and split the data in two.

### 3.2 Path A. The Fly.io beta

Fly.io is a hosting service that runs Docker containers. A Docker image is a sealed box holding Python, the libraries and our code, built from a recipe called a Dockerfile.

1. **The recipe.** It starts from Python 3.12 ([`Dockerfile:8`](../Dockerfile#L8)), installs the libraries ([`Dockerfile:23-24`](../Dockerfile#L23-L24)), copies the `applyfirst` folder and the start script ([`Dockerfile:27-28`](../Dockerfile#L27-L28)), and runs the start script ([`Dockerfile:35`](../Dockerfile#L35)).
2. **The machine.** One machine in Singapore ([`fly.toml:8`](../fly.toml#L8)) with 512 MB of memory ([`fly.toml:77-79`](../fly.toml#L77-L79)). It is never put to sleep, because the worker must keep searching ([`fly.toml:59`](../fly.toml#L59)).
3. **The start script.** It prepares the database tables once ([`entrypoint.sh:13-18`](../entrypoint.sh#L13-L18)), starts the worker in its restart loop ([`entrypoint.sh:30-43`](../entrypoint.sh#L30-L43)), then runs the web app in front ([`entrypoint.sh:46`](../entrypoint.sh#L46)).
4. **Fly's own check** calls `/healthz`, which says "ok" whenever the web app is up ([`fly.toml:63-68`](../fly.toml#L63-L68)). It must stay that simple, because a failing Fly check takes the only machine off the air. The deeper `/health` page is for your outside monitor (section 7).

```sh
# entrypoint.sh:32-42
while :; do
  started=$(date +%s)
  status=0
  python -m applyfirst.saas.worker || status=$?
  ran=$(( $(date +%s) - started ))
  if [ "$ran" -ge 600 ]; then delay=10; fi
  echo "[entrypoint] worker exited with status $status after ${ran}s, restarting in ${delay}s" >&2
  sleep "$delay"
  if [ "$ran" -lt 600 ] && [ "$delay" -lt 300 ]; then delay=$(( delay * 2 )); fi
  if [ "$delay" -gt 300 ]; then delay=300; fi
done
```

**Plain reading.** This is the worker's babysitter. Whenever the worker stops, for any reason, it waits and starts it again. The wait is 10 seconds at first and doubles up to 5 minutes if the worker keeps dying fast. When you read a start script, look for a `while` loop around the program's name. That is what keeps it alive.

The deploy steps are in `Handoff.md` under "Deploy, Path A" and in `docs/OPERATIONS.md`. In short, create the app, create a 1 GB volume in Singapore, set the Google project up, set the secrets with `fly secrets set`, then `fly deploy`.

### 3.3 Path B. The Oracle server

systemd is Linux's built-in manager that starts programs at boot and restarts them when they die. Caddy is a front-door web server that gets and renews the padlock certificate by itself and passes visitors to our app.

1. **Setup** installs Caddy ([`deploy/oracle/setup.sh:26-35`](../deploy/oracle/setup.sh#L26-L35)). It makes `applyfirst`, a system user, which is an account with no login that the app runs as, and puts the code in `/opt/applyfirst` ([`deploy/oracle/setup.sh:37-54`](../deploy/oracle/setup.sh#L37-L54)). It then copies the V1 and V2 unit files into place. A unit file is systemd's instruction card for one program ([`deploy/oracle/setup.sh:69-85`](../deploy/oracle/setup.sh#L69-L85)). The V1 dashboard's unit is not among them. It starts nothing ([`deploy/oracle/setup.sh:7-8`](../deploy/oracle/setup.sh#L7-L8)).
2. **Caddy** sits on the public ports and hands every visitor to the app at `127.0.0.1`, an address only the machine itself can reach ([`deploy/oracle/Caddyfile:17-21`](../deploy/oracle/Caddyfile#L17-L21)).
3. **The web unit** runs uvicorn with 4 copies on `127.0.0.1:8000` ([`deploy/oracle/applyfirst-saas-web.service:20`](../deploy/oracle/applyfirst-saas-web.service#L20)), capped at 480 MB ([`deploy/oracle/applyfirst-saas-web.service:25`](../deploy/oracle/applyfirst-saas-web.service#L25)).
4. **The worker unit** runs the worker about every 330 seconds, give or take 27 percent, and always restarts it ([`deploy/oracle/applyfirst-saas-worker.service:18-22`](../deploy/oracle/applyfirst-saas-worker.service#L18-L22)).
5. **The backup timer** fires daily at 3 in the morning ([`deploy/oracle/applyfirst-saas-backup.timer:6`](../deploy/oracle/applyfirst-saas-backup.timer#L6)).
6. **Settings** come from `/opt/applyfirst/.env`, which V1 and V2 both read ([`deploy/oracle/applyfirst-saas-web.service:14-15`](../deploy/oracle/applyfirst-saas-web.service#L14-L15)). A full template is `deploy/oracle/saas-env.sample`.

Two traps on this path, both found by reading the unit files.

- **Two programs want port 8000.** V1's dashboard already listens on port 8000 ([`deploy/oracle/applyfirst-dash.service:14`](../deploy/oracle/applyfirst-dash.service#L14)), and V2's web unit asks for the same port ([`deploy/oracle/applyfirst-saas-web.service:20`](../deploy/oracle/applyfirst-saas-web.service#L20)). The second one to start fails. Move one of them, and Caddy with it, before using Path B. The runbook does not mention this.
- **The pages would say "about every 10 minutes" while the worker runs about every 5 and a half.** Only the worker unit sets the 330-second interval ([`deploy/oracle/applyfirst-saas-worker.service:18`](../deploy/oracle/applyfirst-saas-worker.service#L18)). The web unit does not, so the pages and the `/health` clock use 600 seconds ([`applyfirst/saas/app.py:50-56`](../applyfirst/saas/app.py#L50-L56)). Add the same setting to the web unit.

### 3.4 V1 on Oracle today

V1 is your personal tool, with its own database and its own settings ([`applyfirst/config.py:43-62`](../applyfirst/config.py#L43-L62)).

1. `applyfirst.service` runs the V1 loop forever ([`deploy/oracle/applyfirst.service:17-19`](../deploy/oracle/applyfirst.service#L17-L19)).
2. Each round searches onlinejobs.ph with the same job reader as V2 ([`applyfirst/cli.py:152`](../applyfirst/cli.py#L152)).
3. It emails **you** through your own mail account, not the Gmail API ([`applyfirst/cli.py:52-58`](../applyfirst/cli.py#L52-L58)).
4. A timer checks every 10 minutes and restarts the loop if it has gone quiet ([`deploy/oracle/applyfirst-health.timer:7-8`](../deploy/oracle/applyfirst-health.timer#L7-L8), [`deploy/oracle/health-check.sh:14-19`](../deploy/oracle/health-check.sh#L14-L19)).
5. A small read-only dashboard is reachable only over Tailscale, a private network between your own devices ([`deploy/oracle/applyfirst-dash.service:11-14`](../deploy/oracle/applyfirst-dash.service#L11-L14)).

The handoff notes add the live facts. The server is an Oracle `VM.Standard.E2.1.Micro` with 1 GB of memory, running Ubuntu 24.04, and all three V1 services are running.

### 3.5 The deployment picture

```mermaid
flowchart TB
  Internet["Browsers on the internet"]
  UR["Uptime monitor"]
  Me["Your phone or laptop<br/>on Tailscale"]

  subgraph Fly["Path A. Fly.io beta (not created yet)"]
    FP["Fly Proxy<br/>padlock on port 443"]
    subgraph M["One machine, shared-cpu-1x, 512 MB"]
      FW["uvicorn web app<br/>port 8080, 1 process"]
      FK["restart loop<br/>runs the worker"]
    end
    Vol[("Volume af_data at /data<br/>applyfirst-saas.db and backups")]
    FP --> FW
    FW --- Vol
    FK --- Vol
  end

  subgraph Oracle["Path B. Oracle VM, /opt/applyfirst"]
    Caddy["Caddy<br/>ports 80 and 443, padlock"]
    SW["V2 web unit<br/>port 8000, 4 processes"]
    SK["V2 worker unit, every 330 s<br/>V2 backup timer, 3 a.m."]
    V1["V1 poll loop, dashboard<br/>and health timer<br/>RUNNING TODAY"]
    Files[(".env, applyfirst.db,<br/>applyfirst-saas.db, backups")]
    Caddy --> SW
    SW --- Files
    SK --- Files
    V1 --- Files
  end

  Internet --> FP
  Internet --> Caddy
  UR -->|"GET /health"| FP
  UR -->|"GET /health"| Caddy
  Me --> V1
```

**How to read it.** There are two possible homes for V2, and only one would be used. Only the box marked "RUNNING TODAY" is live, and that fact comes from the handoff notes, not the code.

### 3.6 The database file and the volume

SQLite is a database that is just one file on disk, with no separate database server. Both programs open it with the same three settings.

```python
# applyfirst/saas/db.py:106-109
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA busy_timeout=10000;")   # ride out web+worker write contention
conn.execute("PRAGMA foreign_keys=ON;")
```

**Plain reading.** `journal_mode=WAL` lets one program read while the other writes. `busy_timeout=10000` means "if the file is busy, wait up to 10 seconds instead of failing". These are why two programs can share one file safely. When a database is shared, look for settings like these right where it is opened.

- The file name comes from `APPLYFIRST_SAAS_DB`, and the code refuses to start if it is set to V1's file name by mistake ([`applyfirst/saas/config.py:123-128`](../applyfirst/saas/config.py#L123-L128)).
- The tables are built and upgraded in numbered steps, now at step 5 ([`applyfirst/saas/db.py:33`](../applyfirst/saas/db.py#L33)). A file newer than the code is refused, so an old copy of the code cannot damage it ([`applyfirst/saas/db.py:121-125`](../applyfirst/saas/db.py#L121-L125)).
- On Fly the volume is 1 GB (the deploy command in `Handoff.md`). Nothing deletes old rows from the `jobs` and `user_job_alerts` tables, only old cached letters are trimmed ([`applyfirst/saas/db.py:771-779`](../applyfirst/saas/db.py#L771-L779)). The operations doc estimates about 940 MB a year at 300 new posts a day ([`docs/OPERATIONS.md:326-327`](../docs/OPERATIONS.md#L326-L327)), so the disk fills within about a year.

### 3.7 Backups

A backup is a dated, compressed copy of the database file. One shared core does the copying for V1 and V2 ([`applyfirst/backup.py:35-71`](../applyfirst/backup.py#L35-L71)).

1. It checks there is room first, and refuses when free disk is under twice the database size ([`applyfirst/backup.py:97-104`](../applyfirst/backup.py#L97-L104)).
2. It takes a safe copy while both programs keep running ([`applyfirst/backup.py:59`](../applyfirst/backup.py#L59)).
3. It compresses into a temporary file, then renames it, so a half-written backup never has a real name ([`applyfirst/backup.py:63-65`](../applyfirst/backup.py#L63-L65)).
4. It keeps the newest 7 and deletes older ones, touching only its own file names ([`applyfirst/backup.py:107-113`](../applyfirst/backup.py#L107-L113)).

| Host | What starts the backup | Where |
|---|---|---|
| Fly | The worker, after its first round of each day | [`applyfirst/saas/worker.py:481-504`](../applyfirst/saas/worker.py#L481-L504), switched on at [`fly.toml:41`](../fly.toml#L41) |
| Oracle, V2 | A systemd timer at 3 in the morning | [`deploy/oracle/applyfirst-saas-backup.timer:6`](../deploy/oracle/applyfirst-saas-backup.timer#L6) |
| Oracle, V1 | The V1 loop, once a day | [`applyfirst/cli.py:84-96`](../applyfirst/cli.py#L84-L96) |

Two honest gaps.

- **On Fly the backups sit on the same disk as the database** ([`fly.toml:36-37`](../fly.toml#L36-L37)). If that disk is lost, both go. A setting exists to copy each backup off the machine, `APPLYFIRST_BACKUP_REMOTE` ([`applyfirst/saas/backup.py:31-37`](../applyfirst/saas/backup.py#L31-L37)), but nothing sets it yet.
- **Nobody has ever restored a backup.** The operations doc says no restore code or procedure exists in the project and writes out the steps the code implies ([`docs/OPERATIONS.md:181-221`](../docs/OPERATIONS.md#L181-L221)). Practise it once before real users depend on it.

### 3.8 Secrets and settings

An environment variable is a named setting handed to a program when it starts. On Fly they come from `fly secrets set` and from the `[env]` block of `fly.toml`. On Oracle and on your PC they come from a `.env` file ([`applyfirst/saas/config.py:121`](../applyfirst/saas/config.py#L121)).

One switch decides "this is production". `APPLYFIRST_SAAS_SECURE_COOKIES` is on unless you turn it off ([`applyfirst/saas/config.py:130`](../applyfirst/saas/config.py#L130)). With it on, the app refuses to start without a real session secret and a real public address.

```python
# applyfirst/saas/config.py:144-146
base_url_raw = os.getenv("APPLYFIRST_BASE_URL")
if secure and (not base_url_raw or "localhost" in base_url_raw or "127.0.0.1" in base_url_raw):
    raise RuntimeError(
```

**Plain reading.** `raise RuntimeError` stops the program before it serves one page. That is on purpose, because a wrong address would break every sign-in. In any settings file, look for `raise`. Those are the settings the program cannot live without.

The settings you must set before a real deploy.

| Setting | What it does | Where |
|---|---|---|
| `SESSION_SECRET` | Signs every cookie and CSRF token (section 6.6). Refuses to start without it | [`applyfirst/saas/config.py:132-142`](../applyfirst/saas/config.py#L132-L142) |
| `APPLYFIRST_BASE_URL` | The public address. Builds Google's return addresses. Must not be localhost | [`applyfirst/saas/config.py:144-151`](../applyfirst/saas/config.py#L144-L151) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Which Google app we are, and its password | [`applyfirst/saas/config.py:155-156`](../applyfirst/saas/config.py#L155-L156) |
| `APPLYFIRST_MASTER_KEY` | The master key that locks every Gmail pass (section 6.5). 32 random bytes written out as plain letters and digits, called base64 | [`applyfirst/saas/crypto.py:61-68`](../applyfirst/saas/crypto.py#L61-L68) |
| `GEMINI_API_KEY` | The Gemini credential. Missing means an alert and `/health` 503 | [`applyfirst/saas/config.py:160`](../applyfirst/saas/config.py#L160) |
| `APPLYFIRST_ALERT_WEBHOOK` | Slack or Discord address for your alerts | [`applyfirst/saas/config.py:170`](../applyfirst/saas/config.py#L170) |
| `APPLYFIRST_SMTP_HOST`, `_USER`, `_PASSWORD` | The server's mail account, for reconnect emails | [`applyfirst/saas/config.py:166-169`](../applyfirst/saas/config.py#L166-L169) |

The full list, with the ones Fly needs, is at the top of [`fly.toml:10-33`](../fly.toml#L10-L33). One warning is written there too. Never set `MASTER_KEY_PATH` on Fly, because it wins over the master key setting and points at a file that does not exist there, so the worker cannot start ([`fly.toml:48-50`](../fly.toml#L48-L50), [`applyfirst/saas/crypto.py:53-54`](../applyfirst/saas/crypto.py#L53-L54)).

Useful defaults, all changeable. 600 seconds between rounds ([`applyfirst/saas/config.py:163`](../applyfirst/saas/config.py#L163)), 10 letters per user per day ([`applyfirst/saas/config.py:162`](../applyfirst/saas/config.py#L162)), `gemini-2.5-flash` as the model ([`applyfirst/saas/config.py:161`](../applyfirst/saas/config.py#L161)), and 20 sign-in requests per address per minute ([`applyfirst/saas/config.py:171-172`](../applyfirst/saas/config.py#L171-L172)).

### 3.9 Monthly cost today

- **V2 costs nothing today**, because nothing is deployed.
- **V1 runs on Oracle's Always Free plan**, so its server costs nothing. Oracle may take back an Always Free machine that looks idle for 7 days ([Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)).
- **The Fly beta will cost about USD 4.30 a month, about PHP 270.** That is USD 4.05 for one shared-cpu-1x 512 MB machine in Singapore, USD 0.15 for the 1 GB volume and pennies of outbound data ([Fly pricing](https://docs.fly.io/about/pricing/)). The operations doc says USD 4.33 ([`docs/OPERATIONS.md:253-254`](../docs/OPERATIONS.md#L253-L254)). Fly has no ongoing free tier.
- **Each AI letter costs about USD 0.003 to 0.007, about PHP 0.17 to 0.40**, depending on how much the model is allowed to think. This is an estimate from Gemini's price list, which charges per token, a piece of text about three quarters of a word. The token counts per letter are **UNVERIFIED** until measured ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)).
- **Sending through the Gmail API is free today** ([Gmail API quota](https://developers.google.com/workspace/gmail/api/reference/quota)).
- **A domain name** is needed for Google's verification. Its price is **UNVERIFIED**.

All money in this guide uses PHP 62.50 per USD, the Bangko Sentral reference rate on 4 September 2026 ([BSP](https://www.bsp.gov.ph/Lists/RERB/Attachments/2349/04Sep2026.pdf)).

---

## 4. What happens when a user signs up

**In short.** A new user makes two separate trips to Google, one to prove who they are and one to allow sending, then fills in the steps the app works out from what they have saved. Pressing Start stamps the moment from which new jobs count as theirs.

### 4.1 Sign in with Google

**The map.** The person clicks Continue with Google. Our server hides three one-time secrets in a sealed cookie and sends the browser to Google. Google sends it back with a one-time code. Our server checks the secrets match, trades the code for Google's signed ID card, checks the card, saves the person and gives them a sign-in cookie.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as Agad web app
    participant G as Google
    participant D as Database
    B->>A: GET /auth/login
    Note over A: make state, nonce and PKCE secrets
    A-->>B: 302 to Google, plus sealed oauth cookie for 10 min
    B->>G: person picks their Google account
    G-->>B: 302 to /auth/callback with code and state
    B->>A: GET /auth/callback with the oauth cookie
    Note over A: returned state must equal the cookie state
    A->>G: trade the code, client secret and PKCE secret
    G-->>A: tokens, including the signed ID card
    A->>G: fetch Google public signing keys, cached
    Note over A: check signature, issuer, audience, expiry, nonce, verified email
    A->>D: insert or update the user by google_sub
    A-->>B: 302 to /dashboard, set session cookie and one-shot note
    B->>A: /dashboard, then /onboarding, then the first missing step
    A-->>B: page shows the Signed in as note, once
```

The hops, in order.

1. The Continue with Google button is a plain link to `/auth/login`, not a form, because the page's safety rules would block a form that jumps to Google ([`applyfirst/saas/templates/_ui.html:63-65`](../applyfirst/saas/templates/_ui.html#L63-L65)).
2. The rate limiter, a counter that turns away anyone asking too often, counts the visit, since every address starting with `/auth/` is limited ([`applyfirst/saas/app.py:235-254`](../applyfirst/saas/app.py#L235-L254)).
3. The server makes three random one-time values ([`applyfirst/saas/google_oauth.py:58-70`](../applyfirst/saas/google_oauth.py#L58-L70)). The **state** proves Google's answer belongs to this browser. The **nonce** must come back inside the ID card. The **PKCE** secret's fingerprint goes to Google now, and the secret itself only later.
4. It builds the Google address asking only for `openid email profile`, meaning name and email and never Gmail ([`applyfirst/saas/google_oauth.py:73-86`](../applyfirst/saas/google_oauth.py#L73-L86)).
5. The three values go into a sealed cookie that lives 10 minutes ([`applyfirst/saas/app.py:395-396`](../applyfirst/saas/app.py#L395-L396), [`applyfirst/saas/session.py:130-134`](../applyfirst/saas/session.py#L130-L134)).
6. Back at `/auth/callback`, a Cancel on Google's page shows the "Sign-in didn't finish" page ([`applyfirst/saas/app.py:403-404`](../applyfirst/saas/app.py#L403-L404)).
7. The state must match exactly, or sign-in ends ([`applyfirst/saas/app.py:409-410`](../applyfirst/saas/app.py#L409-L410)).
8. The code is traded for tokens at Google ([`applyfirst/saas/google_oauth.py:110-127`](../applyfirst/saas/google_oauth.py#L110-L127)).
9. The ID card's signature is checked with Google's public keys, and if the keys cannot be fetched the card is refused, so nobody can force a "skip the check" path ([`applyfirst/saas/google_oauth.py:217-240`](../applyfirst/saas/google_oauth.py#L217-L240)).
10. The card must come from Google, be meant for us, be in date and carry our nonce ([`applyfirst/saas/google_oauth.py:178-190`](../applyfirst/saas/google_oauth.py#L178-L190)), and the email must be verified by Google ([`applyfirst/saas/google_oauth.py:193-202`](../applyfirst/saas/google_oauth.py#L193-L202)).
11. The person is saved by Google's permanent id for them, never by email ([`applyfirst/saas/db.py:220-245`](../applyfirst/saas/db.py#L220-L245)).
12. The reply sets the 7-day sign-in cookie and the one-shot "signed_in" note, deletes the 10-minute cookie and goes to `/dashboard` ([`applyfirst/saas/app.py:424-427`](../applyfirst/saas/app.py#L424-L427)).
13. The first page drawn after that shows "Signed in as ..." and deletes the note in the same reply ([`applyfirst/saas/app.py:315-335`](../applyfirst/saas/app.py#L315-L335)).

```python
# applyfirst/saas/app.py:409-410
if not txn or not returned_state or returned_state != txn.get("state"):
    return _fail(request, cfg_, "state")
```

**Plain reading.** This `if` compares the ticket in the sealed cookie with the ticket in the address. Any mismatch ends the sign-in. In code shaped like this, look first at what is compared, then at what happens on a mismatch.

Every sign-in failure goes through `_fail`, which logs the real reason on the server and shows the same friendly page with status 400 ([`applyfirst/saas/app.py:718-726`](../applyfirst/saas/app.py#L718-L726)). The page reads nothing from the address, so an attacker learns nothing from it ([`applyfirst/saas/templates/signin_failed.html:4-6`](../applyfirst/saas/templates/signin_failed.html#L4-L6)).

### 4.2 Connect Gmail

**The map.** A second, separate trip to Google asks for one extra permission, sending email. What comes back is a long-lived **refresh token**, a reusable pass that lets the worker send later without the person present. It is locked before it touches the database.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as Agad web app
    participant G as Google
    participant D as Database
    B->>A: GET /auth/connect-gmail while signed in
    Note over A: make state and PKCE, no nonce needed
    A-->>B: 302 to Google consent for gmail.send, plus sealed cookie
    B->>G: person ticks Send email on your behalf
    G-->>B: 302 to /auth/gmail-callback with code and state
    B->>A: GET /auth/gmail-callback
    Note over A: returned state must equal the cookie state
    A->>G: trade the code and PKCE secret
    G-->>A: refresh token plus the list of granted permissions
    alt gmail.send missing from the list
        A-->>B: back to Step 1 or dashboard with gmail_error=scope
    else any other failure
        A-->>B: 400, Step 1 page with a retry note
    else success
        Note over A: lock the token with a fresh key, wrapped by the master key
        A->>D: replace the person's Gmail pass row
        A->>D: delete any pending reconnect email record
        A-->>B: 302 to /onboarding with the Gmail connected note
    end
```

The hops, in order.

1. Every Connect Gmail button is a plain link to `/auth/connect-gmail` ([`applyfirst/saas/templates/onboarding_connect_gmail.html:65`](../applyfirst/saas/templates/onboarding_connect_gmail.html#L65), [`applyfirst/saas/templates/dashboard.html:37`](../applyfirst/saas/templates/dashboard.html#L37)).
2. A signed-out visitor is sent to `/login` instead ([`applyfirst/saas/app.py:633-635`](../applyfirst/saas/app.py#L633-L635)).
3. The Google address asks only for `gmail.send`, and asks for a long-lived pass and the consent screen every time ([`applyfirst/saas/google_oauth.py:89-107`](../applyfirst/saas/google_oauth.py#L89-L107)).
4. Back at `/auth/gmail-callback`, a Google error, a state mismatch or a missing code all end the trip ([`applyfirst/saas/app.py:650-658`](../applyfirst/saas/app.py#L650-L658)).
5. The server insists the person really ticked "Send email on your behalf" and that a refresh token came back ([`applyfirst/saas/google_oauth.py:137-156`](../applyfirst/saas/google_oauth.py#L137-L156)).
6. The refresh token is locked and the person's old pass row is replaced, so each person has at most one ([`applyfirst/saas/db.py:279-299`](../applyfirst/saas/db.py#L279-L299)). Section 6.5 explains the lock.
7. Any earlier "your Gmail connection ended" record is wiped, so the person is told again if this new connection ever ends too ([`applyfirst/saas/app.py:671`](../applyfirst/saas/app.py#L671), [`applyfirst/saas/reconnect.py:150-154`](../applyfirst/saas/reconnect.py#L150-L154)).
8. The reply sets the "gmail_connected" note and goes to `/onboarding` ([`applyfirst/saas/app.py:672-675`](../applyfirst/saas/app.py#L672-L675)).

Two failure paths.

- **The box was unticked.** Google returns a pass that cannot send. The code raises a special error ([`applyfirst/saas/google_oauth.py:149-152`](../applyfirst/saas/google_oauth.py#L149-L152)), stores nothing, keeps any earlier working pass and sends the person back with `gmail_error=scope` ([`applyfirst/saas/app.py:690-702`](../applyfirst/saas/app.py#L690-L702)). The page then asks them, calmly, to tick the box ([`applyfirst/saas/templates/_ui.html:135-146`](../applyfirst/saas/templates/_ui.html#L135-L146)).
- **Anything else.** Cancel, a bad state, a failed trade or a locking error all show the same Step 1 page with status 400, and the real reason goes only to the server log ([`applyfirst/saas/app.py:677-688`](../applyfirst/saas/app.py#L677-L688)).

### 4.3 The onboarding router

There is no saved "step number". Every time, `/onboarding` looks at what the person has actually saved and sends them to the first thing missing ([`applyfirst/saas/app.py:519-524`](../applyfirst/saas/app.py#L519-L524)).

```python
# applyfirst/saas/onboarding.py:32-39
if st["activated"]:
    return "done"
if not st["profile_complete"]:
    # Offer Connect Gmail first (skippable); once they're past it, the profile form.
    return "connect_gmail" if not st["gmail_connected"] else "profile"
if st["keyword_count"] == 0:
    return "keywords"
return "preview"
```

**Plain reading.** This is a decision list read from the top, and the first true line wins. Because it reads real data, a person who leaves halfway and comes back lands on the right page. The four facts it reads come from [`applyfirst/saas/onboarding.py:19-26`](../applyfirst/saas/onboarding.py#L19-L26).

### 4.4 The four steps

| Step | What the person does | Rules | Where |
|---|---|---|---|
| 1. Connect Gmail | Connects, or taps "Skip for now", which saves nothing | Shown again next time if they leave before Step 2 | [`applyfirst/saas/app.py:535-540`](../applyfirst/saas/app.py#L535-L540), [`applyfirst/saas/templates/onboarding_connect_gmail.html:68-75`](../applyfirst/saas/templates/onboarding_connect_gmail.html#L68-L75) |
| 2. Profile | Name, job type, subject line, message | 80, 80, 150 and 5,000 characters, checked on the server | [`applyfirst/saas/app.py:557-573`](../applyfirst/saas/app.py#L557-L573), limits at [`applyfirst/saas/app.py:66-67`](../applyfirst/saas/app.py#L66-L67) |
| 3. Watch words | Adds words one at a time or from Quick add | 60 characters each, 20 at most, a repeat is ignored | [`applyfirst/saas/app.py:586-594`](../applyfirst/saas/app.py#L586-L594), [`applyfirst/saas/db.py:403-412`](../applyfirst/saas/db.py#L403-L412) |
| 4. Preview | Sees a sample letter built from their own four fields | No AI, a fixed practice job, free and instant | [`applyfirst/saas/app.py:602-613`](../applyfirst/saas/app.py#L602-L613), [`applyfirst/saas/preview.py:38-50`](../applyfirst/saas/preview.py#L38-L50) |

Details that matter later.

- A good profile save also stores `profile_hash`, a short fingerprint of the four fields used to reuse letters ([`applyfirst/saas/db.py:361-385`](../applyfirst/saas/db.py#L361-L385)).
- On an error the address carries only a fixed error word, never the person's text ([`applyfirst/saas/app.py:84-96`](../applyfirst/saas/app.py#L84-L96)).
- Each watch word stamps `created_at`, the moment it was added ([`applyfirst/saas/db.py:403-412`](../applyfirst/saas/db.py#L403-L412)). The alert rule uses that stamp, so a word removed and added back starts fresh.
- Delete removes a word only when both the word and the signed-in person match, so nobody can delete someone else's word ([`applyfirst/saas/db.py:423-427`](../applyfirst/saas/db.py#L423-L427)).

### 4.5 Activation

1. The Start button posts to `/onboarding/activate` with a CSRF token ([`applyfirst/saas/templates/onboarding_preview.html:64-68`](../applyfirst/saas/templates/onboarding_preview.html#L64-L68)).
2. The route checks again that the profile is complete and there is at least one word ([`applyfirst/saas/app.py:623-627`](../applyfirst/saas/app.py#L623-L627)).
3. `set_activated` stamps `activated_at` only if it is still empty, so the first activation time is kept forever ([`applyfirst/saas/db.py:393-398`](../applyfirst/saas/db.py#L393-L398)).
4. The person lands on the dashboard, which now shows the live panel ([`applyfirst/saas/app.py:629`](../applyfirst/saas/app.py#L629)).

What that switches on in the worker. The worker only searches words that belong to at least one activated person ([`applyfirst/saas/db.py:598-609`](../applyfirst/saas/db.py#L598-L609)), and a job reaches a person only if it was first stored after the latest of their activation, the moment they added that word, and the word's latest baseline ([`applyfirst/saas/db.py:656`](../applyfirst/saas/db.py#L656)). Section 5.4 explains it in full.

A person can press "Start watching without Gmail" on Step 4 ([`applyfirst/saas/templates/onboarding_preview.html:70-87`](../applyfirst/saas/templates/onboarding_preview.html#L70-L87)). Every job found for them is then marked skipped for good, so they get nothing until they connect (section 5.11).

### 4.6 The dashboard

`/dashboard` gathers a few facts and the template shows exactly one big status panel, picked in a fixed order ([`applyfirst/saas/templates/dashboard.html:29-79`](../applyfirst/saas/templates/dashboard.html#L29-L79)).

The colours below are the light-mode ones.

| Panel | Shows when | Main button | Where |
|---|---|---|---|
| Amber | Gmail is not connected | Connect Gmail | [`applyfirst/saas/templates/dashboard.html:30-47`](../applyfirst/saas/templates/dashboard.html#L30-L47) |
| White | No watch words | Add keywords | [`applyfirst/saas/templates/dashboard.html:48-53`](../applyfirst/saas/templates/dashboard.html#L48-L53) |
| Sky blue | Today's letters reached the daily limit | Edit keywords | [`applyfirst/saas/templates/dashboard.html:54-60`](../applyfirst/saas/templates/dashboard.html#L54-L60) |
| Navy, live | Everything else | None | [`applyfirst/saas/templates/dashboard.html:61-78`](../applyfirst/saas/templates/dashboard.html#L61-L78) |

Today's usage is counted per UTC day. UTC is world time, 8 hours behind the Philippines ([`applyfirst/saas/db.py:711-721`](../applyfirst/saas/db.py#L711-L721)), which is why the page says the limit resets at 8 in the morning Philippine time. "Watching since" is the later of activation and the last Gmail reconnect, shown in Philippine time ([`applyfirst/saas/app.py:153-170`](../applyfirst/saas/app.py#L153-L170)).

### 4.7 Log out and Disconnect Gmail

**Log out.**

1. Every signed-in page has a Log out form with a CSRF token ([`applyfirst/saas/templates/base.html:29-32`](../applyfirst/saas/templates/base.html#L29-L32)).
2. The route deletes the sign-in cookie and goes to `/login` ([`applyfirst/saas/app.py:430-434`](../applyfirst/saas/app.py#L430-L434)).
3. The delete repeats every rule the cookie was set with, because a browser ignores a delete of a `__Host-` cookie that leaves out `Secure`. That was an old "Log out did nothing" bug, now fixed ([`applyfirst/saas/session.py:107-110`](../applyfirst/saas/session.py#L107-L110)).

The server keeps no list of live sessions. Log out removes the cookie from that browser, but a copy taken earlier would still work until its 7 days run out ([`applyfirst/saas/session.py:54-69`](../applyfirst/saas/session.py#L54-L69)).

**Disconnect Gmail.**

1. The button sits in a fold-out on the dashboard ([`applyfirst/saas/templates/dashboard.html:119-125`](../applyfirst/saas/templates/dashboard.html#L119-L125)).
2. The route first marks this pass as "switched off on purpose", so the worker never emails the person that their connection "ended" ([`applyfirst/saas/app.py:708`](../applyfirst/saas/app.py#L708)).
3. It unlocks the pass and asks Google to cancel it, best effort ([`applyfirst/saas/app.py:710-714`](../applyfirst/saas/app.py#L710-L714), [`applyfirst/saas/google_oauth.py:159-164`](../applyfirst/saas/google_oauth.py#L159-L164)).
4. It deletes our copy ([`applyfirst/saas/app.py:715`](../applyfirst/saas/app.py#L715), [`applyfirst/saas/db.py:346-348`](../applyfirst/saas/db.py#L346-L348)).
5. From then on the worker marks this person's matches as skipped without spending their daily limit ([`applyfirst/saas/worker.py:181-185`](../applyfirst/saas/worker.py#L181-L185)).

---

## 5. The engine that finds jobs and sends applications

**In short.** About every 10 minutes the worker searches onlinejobs.ph once per watch word, stores new jobs, decides which users each new job is for, has Gemini write each letter and sends it from each user's Gmail to themselves. Almost all of it is in `applyfirst/saas/worker.py`, and every database step goes through `applyfirst/saas/db.py`.

Four words used all through this section.

- A **round** (the code says cycle) is one full pass of search, decide, write and send.
- An **alert** is one row that means "send this job to this user". It has a status, like pending or sent ([`applyfirst/saas/db.py:448-462`](../applyfirst/saas/db.py#L448-L462)).
- A **baseline** is a search that stores what is already posted and tells nobody.
- A **log event** is one line the worker writes about what just happened, like `search_failed`.

### 5.1 One round, in a picture

```mermaid
flowchart TD
    S["Round starts<br/>watchdog armed"] --> P["AI instructions changed?<br/>then wipe the saved letters"]
    P --> W["List every watch word<br/>of every activated user, once each"]
    W --> N{"Another word?"}
    N -->|yes| G["Polite pause<br/>1.0 to 2.5 s"]
    G --> Q["Search onlinejobs.ph<br/>for this word"]
    Q -->|"search failed"| N
    Q --> B{"Does this word<br/>need a baseline?"}
    B -->|yes| BS["Store each new job<br/>fetch its full page<br/>tell nobody"]
    B -->|no| FS["Store each new job<br/>fetch its full page"]
    FS --> F["alert_watchers<br/>one pending alert per watcher<br/>who started before the job was stored"]
    BS --> M["Stamp the word as searched"]
    F --> M
    M --> N
    N -->|"no more words"| Z{"Words searched<br/>but zero jobs in total?"}
    Z -->|yes| C["Canary search<br/>for virtual assistant"]
    Z -->|no| A
    C --> A["Each pending alert, oldest first<br/>check, cap, tailor, compose, send"]
    A --> R["Email users whose<br/>Gmail connection ended"]
    R --> T["Log cycle_complete<br/>count AI failures"]
    T --> H["Heartbeat<br/>and blind count"]
    H --> U["Throw away old saved letters"]
    U --> K["Take today's backup<br/>if due"]
    K --> D["Watchdog disarmed<br/>sleep about 10 minutes"]
    D --> S
```

The round itself is `run_once` ([`applyfirst/saas/worker.py:240`](../applyfirst/saas/worker.py#L240)). The housekeeping after it is in `_cycle` ([`applyfirst/saas/worker.py:558-569`](../applyfirst/saas/worker.py#L558-L569)).

### 5.2 How the worker starts and sleeps

1. It reads the settings and switches logging on first ([`applyfirst/saas/worker.py:580-581`](../applyfirst/saas/worker.py#L580-L581)).
2. It loads the master key. Without it, it alerts you and quits ([`applyfirst/saas/worker.py:582-597`](../applyfirst/saas/worker.py#L582-L597)).
3. It builds the onlinejobs.ph reader ([`applyfirst/saas/worker.py:599-603`](../applyfirst/saas/worker.py#L599-L603)) and runs its start-up checks, which shout once when a production worker is missing the alert channel, the mail settings or the Gemini credential ([`applyfirst/saas/worker.py:445-478`](../applyfirst/saas/worker.py#L445-L478)).
4. It starts the watchdog, a timer that ends a stuck round (section 7.3), and loops forever ([`applyfirst/saas/worker.py:611-620`](../applyfirst/saas/worker.py#L611-L620)).

Between rounds it sleeps the interval plus or minus a random share. By default that is 600 seconds plus or minus 25 percent, so 7.5 to 12.5 minutes ([`applyfirst/saas/config.py:47-48`](../applyfirst/saas/config.py#L47-L48), [`applyfirst/saas/worker.py:619`](../applyfirst/saas/worker.py#L619)). The sleep starts after the round ends, so a long round quietly pushes everything later.

To run exactly one round and stop, use `python -m applyfirst.saas.worker --once` ([`applyfirst/saas/worker.py:607`](../applyfirst/saas/worker.py#L607)).

### 5.3 Searching and storing jobs

The list of words to search comes from one database question.

```sql
-- applyfirst/saas/db.py:602-606
SELECT DISTINCT k.keyword
FROM user_keywords k
JOIN user_profiles p ON p.user_id = k.user_id
WHERE k.is_active = 1 AND p.activated_at IS NOT NULL
ORDER BY k.keyword
```

**Plain reading.** `JOIN` links each watch word to its owner's profile. `activated_at IS NOT NULL` keeps only people who pressed Start. `DISTINCT` means a word watched by 50 people is searched once, not 50 times. When you read a database query, look at the `WHERE` line first, because it decides who is in and who is out.

`DISTINCT` compares exactly, so "Shopify" and "shopify" are two searches ([`applyfirst/saas/db.py:198`](../applyfirst/saas/db.py#L198)).

1. **Polite pauses.** 1.0 to 2.5 seconds between words and 0.3 to 0.8 seconds after each full job page ([`applyfirst/saas/worker.py:57-58`](../applyfirst/saas/worker.py#L57-L58)). onlinejobs.ph asks for 5 seconds (section 9.1).
2. **The search.** It opens the same address you get by typing the word into the site's search box ([`applyfirst/sources/onlinejobsph.py:55-57`](../applyfirst/sources/onlinejobsph.py#L55-L57)) and reads each job card from the page ([`applyfirst/sources/onlinejobsph.py:120-161`](../applyfirst/sources/onlinejobsph.py#L120-L161)).
3. **A failed search** is logged as `search_failed` and the word is skipped for this round ([`applyfirst/saas/worker.py:264-266`](../applyfirst/saas/worker.py#L264-L266)).
4. **Storing.** The `jobs` table is shared by everyone. A job already stored is not fetched again ([`applyfirst/saas/worker.py:114-118`](../applyfirst/saas/worker.py#L114-L118)). A new one gets its full page fetched once ([`applyfirst/saas/worker.py:122`](../applyfirst/saas/worker.py#L122)).
5. **Size limit.** The job text is cut to 8,000 characters, so one giant post cannot blow up the AI bill ([`applyfirst/saas/worker.py:59`](../applyfirst/saas/worker.py#L59), [`applyfirst/saas/worker.py:131`](../applyfirst/saas/worker.py#L131)).
6. **The stamp.** `insert_job` stamps `scraped_at` with the time right now, to the second ([`applyfirst/saas/db.py:573-588`](../applyfirst/saas/db.py#L573-L588)). This stamp is what the alert rule compares against.

### 5.4 The fan-out rule, and why it exists

Fan-out means turning one job into one alert for each person who should get it. This rule was fixed on 27 September 2026 and is not committed yet. It is described here as it is on disk.

**The rule.** A person hears about a job only if Agad first stored it after the latest of three moments. When they pressed Start. When they added that watch word. The word's latest baseline.

**The proof, hop by hop.**

1. Before storing a word's results, the worker asks whether this search is a baseline ([`applyfirst/saas/worker.py:269`](../applyfirst/saas/worker.py#L269)).
2. A word needs a baseline if it was never searched, or if nobody watching it now was watching at its last search ([`applyfirst/saas/db.py:784-804`](../applyfirst/saas/db.py#L784-L804)).
3. On a baseline, jobs are stored and nobody is told ([`applyfirst/saas/worker.py:274-275`](../applyfirst/saas/worker.py#L274-L275)).
4. Otherwise each job goes to `alert_watchers` ([`applyfirst/saas/worker.py:278`](../applyfirst/saas/worker.py#L278)), which keeps only the watchers who started before the job was stored ([`applyfirst/saas/db.py:636-665`](../applyfirst/saas/db.py#L636-L665)).
5. After the search the word is stamped, and a baseline also moves the word's baseline stamp to now ([`applyfirst/saas/worker.py:279`](../applyfirst/saas/worker.py#L279), [`applyfirst/saas/db.py:807-821`](../applyfirst/saas/db.py#L807-L821)).

```sql
-- applyfirst/saas/db.py:655-658
WHERE k.is_active = 1 AND k.keyword = ? AND p.activated_at IS NOT NULL
  AND j.scraped_at > MAX(p.activated_at, k.created_at, s.baselined_at)
  AND NOT EXISTS (SELECT 1 FROM user_job_alerts a
                  WHERE a.user_id = k.user_id AND a.job_id = j.id)
```

**Plain reading.** `MAX(...)` picks the latest of the three start moments, and the job must be strictly newer. The last two lines skip anyone who already has this job, so a quiet repeat search writes nothing. When you read a rule like this, find the comparison sign first, here `>`, then read what sits on each side.

```python
# applyfirst/saas/db.py:801-804
if row is None or row["baselined_at"] is None:
    return False
first_start = row["first_start"]
return first_start is None or (row["last_polled"] or "") >= first_start
```

**Plain reading.** `False` here means "do a baseline". It happens when the word was never searched, or when its last search came before any of its current watchers started. `first_start` is the earliest moment a current watcher began, worked out as the later of their activation and when they added the word ([`applyfirst/saas/db.py:793`](../applyfirst/saas/db.py#L793)). So a word nobody watched for a week, then someone adds again, gets a fresh quiet look instead of dumping a week of posts on them.

**A small example.** Ana presses Start at 9 in the morning and adds "shopify" five minutes later. The word gets its baseline a minute after that. Job X was first stored at half past eight through someone else's word, so it is old news to Ana. Job Y is first stored at twenty past nine, so Ana gets it.

**Why it exists.** Before the fix, every search after the first alerted the whole results page to every watcher. A search page mostly repeats jobs an earlier search already stored. On 26 September a new user got 59 alerts in one go, mostly old jobs ([`docs/SYSTEM-DESIGN.md:350-353`](../docs/SYSTEM-DESIGN.md#L350-L353), and the code comment at [`applyfirst/saas/db.py:643-645`](../applyfirst/saas/db.py#L643-L645)). Old jobs are useless to someone who wants to be first, and each one would have spent one of their 10 daily letters.

**One edge.** Stamps are to the second, so a job stored in the very same second as the start is left out ([`applyfirst/saas/db.py:643-644`](../applyfirst/saas/db.py#L643-L644)).

**The guards.** Each case has its own test in `tests/test_saas_worker.py`. Baseline jobs never alert later ([`tests/test_saas_worker.py:101`](../tests/test_saas_worker.py#L101)). A newcomer gets only newer jobs ([`tests/test_saas_worker.py:133`](../tests/test_saas_worker.py#L133)). Removing and re-adding a word restarts its clock ([`tests/test_saas_worker.py:162`](../tests/test_saas_worker.py#L162)). No backlog after a gap ([`tests/test_saas_worker.py:189`](../tests/test_saas_worker.py#L189), [`tests/test_saas_worker.py:220`](../tests/test_saas_worker.py#L220)). A quiet search writes nothing ([`tests/test_saas_worker.py:246`](../tests/test_saas_worker.py#L246)). Each watcher keeps their own start ([`tests/test_saas_worker.py:267`](../tests/test_saas_worker.py#L267)). The same-second edge ([`tests/test_saas_worker.py:292`](../tests/test_saas_worker.py#L292)).

The table allows one alert per person per job, even if two of their words match it ([`applyfirst/saas/db.py:459`](../applyfirst/saas/db.py#L459)). Gmail is not checked at this point. Someone without Gmail still gets an alert, and the next step marks it skipped.

### 5.5 Handling each alert

The worker takes every pending alert, oldest first, across all users, one at a time ([`applyfirst/saas/worker.py:288-298`](../applyfirst/saas/worker.py#L288-L298)). For each one, `process_alert` goes in this order ([`applyfirst/saas/worker.py:171-228`](../applyfirst/saas/worker.py#L171-L228)).

1. Not activated? Mark it skipped ([`applyfirst/saas/worker.py:175`](../applyfirst/saas/worker.py#L175)).
2. No Gmail pass? Mark it skipped, before any AI work, so no daily letter is spent on someone who cannot receive it ([`applyfirst/saas/worker.py:181-185`](../applyfirst/saas/worker.py#L181-L185)).
3. Write the letter ([`applyfirst/saas/worker.py:187-190`](../applyfirst/saas/worker.py#L187-L190), sections 5.6 and 5.7).
4. Build the email ([`applyfirst/saas/worker.py:195`](../applyfirst/saas/worker.py#L195)).
5. Send it, and on success mark it sent with the time ([`applyfirst/saas/worker.py:200-227`](../applyfirst/saas/worker.py#L200-L227)).

A safety net catches any surprise error for one alert, marks that one failed and moves on, so one bad alert never stops the others ([`applyfirst/saas/worker.py:292-295`](../applyfirst/saas/worker.py#L292-L295)).

### 5.6 Writing the letter with Gemini

1. The worker builds a letter engine with Gemini plugged in if a credential is set, or with no AI if not ([`applyfirst/saas/worker.py:83-88`](../applyfirst/saas/worker.py#L83-L88)).
2. The person's four answers are turned into the shape the engine expects. The standard message becomes the base pitch and the subject becomes the saved subject line ([`applyfirst/saas/preview.py:23-35`](../applyfirst/saas/preview.py#L23-L35)).
3. The engine is always told no resume is attached, because the SaaS never sends a resume file ([`applyfirst/saas/worker.py:156-162`](../applyfirst/saas/worker.py#L156-L162)).
4. The engine makes two texts, the rules and the data, and tries Gemini up to twice ([`applyfirst/tailor/engine.py:84-100`](../applyfirst/tailor/engine.py#L84-L100)).
5. The rules text says to use only true facts from the profile, to treat the job post as untrusted text and never obey it ([`applyfirst/tailor/prompt.py:54-55`](../applyfirst/tailor/prompt.py#L54-L55)), and to keep the user's own message format ([`applyfirst/tailor/prompt.py:62`](../applyfirst/tailor/prompt.py#L62)).
6. The data text wraps the profile and the job post each in a fence with a random tag, so words inside a post cannot fake the "end of post" marker and sneak in orders ([`applyfirst/tailor/prompt.py:131-137`](../applyfirst/tailor/prompt.py#L131-L137)).
7. The answer must fit a fixed shape. A digest of what the employer wants, a subject line, screening questions with drafted answers, an optional "start your reply with" word, and the cover letter ([`applyfirst/tailor/contract.py:28-34`](../applyfirst/tailor/contract.py#L28-L34)).

```python
# applyfirst/tailor/llm.py:34-41
body = {
    "system_instruction": {"parts": [{"text": system}]},
    "contents": [{"role": "user", "parts": [{"text": user}]}],
    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
}
# The credential rides in a header, never the URL, so no URL an HTTP library logs or
# an error message repeats can ever carry it.
resp = self._client.post(url, headers={"x-goog-api-key": self.api_key}, json=body)
```

**Plain reading.** This is the only place the product talks to Gemini. `body` is the whole request, the rules, the data and two settings. The credential travels in a header, a hidden label on the request, so it never lands in a log. Notice what the request does not set. There is no limit on the model's hidden "thinking", which is billed like normal output (section 9.3).

**When the AI is off or fails.** With no credential, or after two failed tries, the letter is the person's own message word for word, labelled `rules-fallback` ([`applyfirst/tailor/engine.py:110-140`](../applyfirst/tailor/engine.py#L110-L140)). If the post asks for a resume it adds "I can send my resume on request." ([`applyfirst/tailor/engine.py:137`](../applyfirst/tailor/engine.py#L137)). The email then carries a line saying the AI was unavailable, so the person edits before sending ([`applyfirst/notify/compose.py:89`](../applyfirst/notify/compose.py#L89)).

**The saved-letter cache.** Each finished letter is saved, keyed by the job and the profile fingerprint ([`applyfirst/saas/db.py:472-479`](../applyfirst/saas/db.py#L472-L479)), so a retry never pays twice. At the start of every round the worker compares a fingerprint of the AI instructions with the one it saved. If they differ, it empties the whole cache, so a letter written under old instructions is never re-sent ([`applyfirst/saas/worker.py:91-106`](../applyfirst/saas/worker.py#L91-L106)). Saved letters older than 30 days are thrown away after every round ([`applyfirst/saas/db.py:771-779`](../applyfirst/saas/db.py#L771-L779)).

**The email.** The subject is the job title, its type and "onlinejobs.ph" ([`applyfirst/notify/compose.py:82`](../applyfirst/notify/compose.py#L82)). The body holds the job facts and apply link, the subject to paste, the ready-to-paste letter and the screening answers ([`applyfirst/notify/compose.py:83-106`](../applyfirst/notify/compose.py#L83-L106)). Every piece of job or AI text is escaped in the HTML, so a job post cannot plant code in the email ([`applyfirst/notify/compose.py:111`](../applyfirst/notify/compose.py#L111)).

### 5.7 The daily cap and free retries

```python
# applyfirst/saas/worker.py:144-153
cached = db.cache_get(conn, alert.job_id, profile.profile_hash)
if cached is not None:
    package = TailoredPackage.model_validate_json(cached["package_json"])
    return package, cached["provider"], cached["provider"] != "rules-fallback"

if cfg.daily_tailor_cap <= 0:
    return None  # AI switched off (APPLYFIRST_DAILY_TAILOR_CAP=0), retries included
if alert.attempts == 0 and not db.try_increment_ai_usage(conn, alert.user_id,
                                                         cfg.daily_tailor_cap):
    return None  # daily cap reached
```

**Plain reading.** A saved letter is used first and is free. A cap of 0 switches letter writing off for everyone. Only a first try (`attempts == 0`) takes one of the day's slots. A retry was already paid for, so it re-writes for free even if the person hit the cap since.

- The counter adds one only while the count is under the cap, in one indivisible database step, so two things running at once cannot both slip past ([`applyfirst/saas/db.py:691-708`](../applyfirst/saas/db.py#L691-L708)).
- The day is the UTC date, so in the Philippines the count starts fresh at 8 in the morning ([`applyfirst/saas/db.py:695`](../applyfirst/saas/db.py#L695)).
- One slot is one job, not one AI call. The engine may call Gemini twice for one job ([`applyfirst/tailor/engine.py:80`](../applyfirst/tailor/engine.py#L80)).
- A job that hits the cap is marked `capped`, and that is final. It is not sent tomorrow either ([`applyfirst/saas/db.py:668-670`](../applyfirst/saas/db.py#L668-L670)).

### 5.8 Statuses and retries

An alert has one of five statuses, and the database refuses anything else ([`applyfirst/saas/db.py:453-454`](../applyfirst/saas/db.py#L453-L454)).

```mermaid
stateDiagram-v2
    [*] --> pending: alert_watchers makes the row
    pending --> pending: send hiccup, under 3 tries
    pending --> sent: Gmail took the email
    pending --> failed: 3rd hiccup, Gmail pass died, or surprise error
    pending --> capped: daily slots used up
    pending --> skipped: not activated or no Gmail
    sent --> [*]
    failed --> [*]
    capped --> [*]
    skipped --> [*]
```

**How retries work.** Each hiccup adds one to the try count ([`applyfirst/saas/worker.py:231-237`](../applyfirst/saas/worker.py#L231-L237)). On the third try (`_MAX_ATTEMPTS = 3`, [`applyfirst/saas/worker.py:50`](../applyfirst/saas/worker.py#L50)) the alert fails for good. Before that it stays pending and the next round, about 10 minutes later, tries again.

### 5.9 Sending through Gmail

1. Before it writes the letter, the worker unlocks the person's pass, in memory only ([`applyfirst/saas/worker.py:181-182`](../applyfirst/saas/worker.py#L181-L182), [`applyfirst/saas/db.py:326-343`](../applyfirst/saas/db.py#L326-L343)).
2. It trades the long-lived pass for a short-lived access token at Google ([`applyfirst/saas/gmail_send.py:38-69`](../applyfirst/saas/gmail_send.py#L38-L69)).
3. It builds the message with From and To both set to the person's own address ([`applyfirst/saas/gmail_send.py:75`](../applyfirst/saas/gmail_send.py#L75)) and posts it to Gmail's send address ([`applyfirst/saas/gmail_send.py:95`](../applyfirst/saas/gmail_send.py#L95)).
4. It sorts failures into two kinds. **The pass is dead** when Google says `invalid_grant` or the permission is missing ([`applyfirst/saas/gmail_send.py:67`](../applyfirst/saas/gmail_send.py#L67), [`applyfirst/saas/gmail_send.py:114`](../applyfirst/saas/gmail_send.py#L114)). **Try again later** is everything else, including a rate-limit 403 ([`applyfirst/saas/gmail_send.py:116`](../applyfirst/saas/gmail_send.py#L116)). Throwing away a good pass over a rate limit would be wrong, so that split is on purpose.

### 5.10 When Google ends a Gmail connection

**Why this exists.** While the Google app is in Testing mode, Google kills every Gmail pass 7 days after the person connects ([`applyfirst/saas/reconnect.py:1-9`](../applyfirst/saas/reconnect.py#L1-L9)). Before this fix, called B6, the person simply stopped getting applications and nobody told them. Their own Gmail cannot carry the news, because that is the connection that just died. So the worker emails them from the server's own mail account.

```mermaid
sequenceDiagram
    autonumber
    participant W as Worker
    participant G as Gmail API
    participant D as Database
    participant S as Server mail account
    participant U as User inbox
    W->>G: send the letter with the user's pass
    G-->>W: invalid_grant, the pass is dead
    W->>D: did the connected time change during the send?
    alt it changed
        Note over W,D: the user reconnected mid-send, retry next round
    else it did not change
        W->>D: queue a reconnect row, due
        W->>D: delete the dead pass only if it is still the same one
        W->>D: mark this alert failed
    end
    Note over W: after every alert in the round
    W->>D: read due rows, least recently tried first
    W->>S: send Your Gmail connection ended
    S-->>U: email with a link to the dashboard
    W->>D: mark the row sent
```

The hops, in order.

1. The worker catches the dead-pass error ([`applyfirst/saas/worker.py:201`](../applyfirst/saas/worker.py#L201)).
2. If the connection time changed during the send, it is not an expiry, and the alert is retried ([`applyfirst/saas/worker.py:202-205`](../applyfirst/saas/worker.py#L202-L205)).
3. It queues the email first, as one row in `worker_meta` ([`applyfirst/saas/worker.py:209`](../applyfirst/saas/worker.py#L209), [`applyfirst/saas/reconnect.py:123-140`](../applyfirst/saas/reconnect.py#L123-L140)). Nothing is queued if the person disconnected on purpose or was already told about this very connection ([`applyfirst/saas/reconnect.py:134`](../applyfirst/saas/reconnect.py#L134)).
4. It deletes the dead pass only if it is still the same one, so a reconnect that landed a moment ago is kept ([`applyfirst/saas/worker.py:211`](../applyfirst/saas/worker.py#L211), [`applyfirst/saas/reconnect.py:157-167`](../applyfirst/saas/reconnect.py#L157-L167)).
5. After all alerts it sends every queued email ([`applyfirst/saas/worker.py:300`](../applyfirst/saas/worker.py#L300), [`applyfirst/saas/reconnect.py:290`](../applyfirst/saas/reconnect.py#L290)), through the server's mail account ([`applyfirst/saas/reconnect.py:223-249`](../applyfirst/saas/reconnect.py#L223-L249)). The email links to the dashboard ([`applyfirst/saas/reconnect.py:205`](../applyfirst/saas/reconnect.py#L205)).

If the mail server itself fails, sending pauses 15 minutes, then 1 hour, then 6 hours ([`applyfirst/saas/reconnect.py:63`](../applyfirst/saas/reconnect.py#L63)). If only one message is refused, that one person waits on a slower clock of their own ([`applyfirst/saas/reconnect.py:183`](../applyfirst/saas/reconnect.py#L183)). The worker gives up on a person only after 3 days of refusals, and only if some other email got through in that time ([`applyfirst/saas/reconnect.py:344`](../applyfirst/saas/reconnect.py#L344)). You are alerted in each of these cases ([`applyfirst/saas/worker.py:316-357`](../applyfirst/saas/worker.py#L316-L357)).

To test it after a deploy, run `python -m applyfirst.saas.reconnect --test you@example.com` ([`applyfirst/saas/reconnect.py:364`](../applyfirst/saas/reconnect.py#L364)).

### 5.11 Gaps in the engine

These are true of the code as it is now.

- **Jobs found while Gmail is off are lost.** The alert becomes skipped, and skipped is final ([`applyfirst/saas/worker.py:184`](../applyfirst/saas/worker.py#L184), [`applyfirst/saas/db.py:668-670`](../applyfirst/saas/db.py#L668-L670)). After reconnecting, the person gets only jobs found from then on.
- **A capped job is never sent later** (section 5.7).
- **A word's first search fetches the full page of every job it finds**, about 30, even though a baseline tells nobody ([`applyfirst/saas/worker.py:114-132`](../applyfirst/saas/worker.py#L114-L132)). One person adding 20 new words can add about 15 minutes to one round ([`docs/OPERATIONS.md:298-300`](../docs/OPERATIONS.md#L298-L300)).
- **After an outage, every pending alert is handled one after another in one round**, with no limit per round ([`docs/OPERATIONS.md:302-304`](../docs/OPERATIONS.md#L302-L304)).
- **Failed sends never show on `/health`** (section 7.1).

---

## 6. Data and safety

**In short.** Everything lives in 11 tables in one SQLite file. The one dangerous thing in it, each person's Gmail sending pass, is locked with a key that never enters the file. Pages are protected by signed cookies, CSRF tokens (section 6.6), a strict CSP, which is a rule list for the browser (section 6.7), and a sign-in rate limit. The honest gaps are listed at the end.

### 6.1 The tables

| Table | What it is for | Belongs to one person | Created at |
|---|---|---|---|
| `users` | One row per Google account. Google id, email, display name, plan | yes | [`applyfirst/saas/db.py:147`](../applyfirst/saas/db.py#L147) |
| `oauth_credentials` | The locked Gmail pass | yes | [`applyfirst/saas/db.py:156`](../applyfirst/saas/db.py#L156) |
| `user_profiles` | The four answers, their fingerprint and the Start time | yes | [`applyfirst/saas/db.py:181`](../applyfirst/saas/db.py#L181) |
| `user_keywords` | The watch words and when each was added | yes | [`applyfirst/saas/db.py:195`](../applyfirst/saas/db.py#L195) |
| `jobs` | One shared pool of public onlinejobs.ph posts | no | [`applyfirst/saas/db.py:436`](../applyfirst/saas/db.py#L436) |
| `user_job_alerts` | "This job is for this person", with status and tries | yes | [`applyfirst/saas/db.py:448`](../applyfirst/saas/db.py#L448) |
| `ai_usage` | Letters written per person per day | yes | [`applyfirst/saas/db.py:464`](../applyfirst/saas/db.py#L464) |
| `tailoring_cache` | Letters already written, reused for the same job and profile | no | [`applyfirst/saas/db.py:472`](../applyfirst/saas/db.py#L472) |
| `worker_keyword_state` | When each word was last searched and last baselined | no | [`applyfirst/saas/db.py:483`](../applyfirst/saas/db.py#L483) |
| `worker_meta` | The shared notebook between the two programs | no | [`applyfirst/saas/db.py:489`](../applyfirst/saas/db.py#L489) |
| `auth_rate_hits` | The sign-in speed limit counter | no | [`applyfirst/saas/db.py:506`](../applyfirst/saas/db.py#L506) |

The rules that stop duplicates. One account per Google id ([`applyfirst/saas/db.py:149`](../applyfirst/saas/db.py#L149)), one profile per person ([`applyfirst/saas/db.py:183`](../applyfirst/saas/db.py#L183)), one copy of each word per person ([`applyfirst/saas/db.py:201`](../applyfirst/saas/db.py#L201)), one copy of each onlinejobs.ph post ([`applyfirst/saas/db.py:438`](../applyfirst/saas/db.py#L438)), one alert per person per job ([`applyfirst/saas/db.py:459`](../applyfirst/saas/db.py#L459)) and one saved letter per job and profile ([`applyfirst/saas/db.py:479`](../applyfirst/saas/db.py#L479)).

Four columns exist but nothing fills them. `refresh_token_tag` ([`applyfirst/saas/db.py:163`](../applyfirst/saas/db.py#L163)), `access_token_expiry` ([`applyfirst/saas/db.py:166`](../applyfirst/saas/db.py#L166)), `profile_extras_json` ([`applyfirst/saas/db.py:188`](../applyfirst/saas/db.py#L188)), and `plan`, which is always written as free ([`applyfirst/saas/db.py:234`](../applyfirst/saas/db.py#L234)). No billing exists yet.

The data drawing in `docs/SYSTEM-DESIGN.md` is older than the code. It shows an `applications` table and other columns that were never built. Trust the diagram below, which is drawn from the code.

### 6.2 The data diagram, as built

It shows the key columns only. Solid lines are links the database enforces. Dotted lines are matches by value that the code relies on but the database does not enforce.

```mermaid
erDiagram
    users ||--o{ oauth_credentials : "has Gmail pass"
    users ||--o| user_profiles : "has"
    users ||--o{ user_keywords : "watches"
    users ||--o{ user_job_alerts : "receives"
    users ||--o{ ai_usage : "is counted in"
    jobs ||--o{ user_job_alerts : "fans out to"
    jobs ||--o{ tailoring_cache : "has saved letters"
    user_keywords }o..o| worker_keyword_state : "same word text"
    user_profiles }o..o{ tailoring_cache : "same profile_hash"

    users {
        TEXT id PK
        TEXT google_sub UK "Google id, the login key"
        TEXT email "where letters are sent"
        TEXT plan "always free today"
    }
    oauth_credentials {
        TEXT user_id FK
        BLOB refresh_token_ciphertext "locked pass"
        BLOB encrypted_dek "locked data key"
        TEXT updated_at "connected at"
    }
    user_profiles {
        TEXT user_id FK
        TEXT standard_message "one of the 4 answers"
        TEXT profile_hash "sha256 of the 4 answers"
        TEXT activated_at "empty until Start"
    }
    user_keywords {
        TEXT user_id FK
        TEXT keyword "unique per user"
        TEXT created_at "the word start clock"
    }
    jobs {
        TEXT id PK
        TEXT onlinejobs_id UK "the site id"
        TEXT raw_description "max 8000 chars"
        TEXT scraped_at "first stored"
    }
    user_job_alerts {
        TEXT user_id FK
        TEXT job_id FK
        TEXT status "pending sent failed capped skipped"
        INTEGER attempts
    }
    ai_usage {
        TEXT user_id PK
        TEXT day PK "UTC date"
        INTEGER tailoring_calls
    }
    tailoring_cache {
        TEXT job_id FK
        TEXT profile_hash
        TEXT package_json "the written letter"
    }
    worker_keyword_state {
        TEXT keyword PK
        TEXT baselined_at
        TEXT last_polled
    }
    worker_meta {
        TEXT key PK
        TEXT value
    }
    auth_rate_hits {
        TEXT bucket PK "address and time window"
        INTEGER hits
    }
```

### 6.3 Keeping one person's data apart from another's

A tenant is one customer's private slice of a shared system, like one flat in an apartment block. Five tables carry a `user_id` and are listed as tenant tables ([`applyfirst/saas/db.py:28-31`](../applyfirst/saas/db.py#L28-L31)). Almost every read goes through a `db.py` function that takes the user id and filters by it, for example [`applyfirst/saas/db.py:415-427`](../applyfirst/saas/db.py#L415-L427). A helper that adds `AND user_id = ?` exists ([`applyfirst/saas/tenant.py:33-49`](../applyfirst/saas/tenant.py#L33-L49)), and it answers "not found" rather than "forbidden", so a stranger cannot even learn a row exists.

There is no second wall inside the database, because that feature belongs to Postgres, a bigger database server, and the app runs on SQLite. The function filters, plus a test that signs in as Bob, asks for Alice's data and requires "not found", are the whole defence ([`tests/test_saas_cross_tenant.py:37`](../tests/test_saas_cross_tenant.py#L37)).

### 6.4 What personal data is kept, and for how long

| What | Where | How long | Proof |
|---|---|---|---|
| Google id, email, display name | `users` | Forever. Nothing deletes the row | [`applyfirst/saas/db.py:147-154`](../applyfirst/saas/db.py#L147-L154) |
| Name, job type, subject, message | `user_profiles` | Forever, overwritten on each edit | [`applyfirst/saas/db.py:361-385`](../applyfirst/saas/db.py#L361-L385) |
| Watch words | `user_keywords` | Until the person removes one | [`applyfirst/saas/db.py:423-427`](../applyfirst/saas/db.py#L423-L427) |
| Gmail pass, locked | `oauth_credentials` | Until Disconnect, expiry or a reconnect replaces it | [`applyfirst/saas/app.py:715`](../applyfirst/saas/app.py#L715), [`applyfirst/saas/worker.py:211`](../applyfirst/saas/worker.py#L211) |
| Which jobs matched, and error text | `user_job_alerts` | Forever, never pruned | [`applyfirst/saas/db.py:448-462`](../applyfirst/saas/db.py#L448-L462) |
| Letters written per day | `ai_usage` | Forever, never pruned | [`applyfirst/saas/db.py:464-470`](../applyfirst/saas/db.py#L464-L470) |
| The written letters | `tailoring_cache` | At most 30 days | [`applyfirst/saas/db.py:771-779`](../applyfirst/saas/db.py#L771-L779) |
| Sign-in request addresses | `auth_rate_hits` | About two minutes | [`applyfirst/saas/db.py:737-748`](../applyfirst/saas/db.py#L737-L748) |
| Who is signed in | a browser cookie holding only the user id | 7 days | [`applyfirst/saas/session.py:28`](../applyfirst/saas/session.py#L28) |
| Event logs | Fly logs or the Oracle journal | As long as the host keeps them. User id and words, never emails or letters | [`applyfirst/log.py:50-60`](../applyfirst/log.py#L50-L60) |
| Whole-database copies | the backups folder | The last 7 | [`applyfirst/backup.py:107-113`](../applyfirst/backup.py#L107-L113) |
| The sent email | the person's own Gmail | Up to the person | [`applyfirst/saas/gmail_send.py:72-81`](../applyfirst/saas/gmail_send.py#L72-L81) |

A saved letter can be shared by two people only if their four answers are identical, because the key is a fingerprint of exactly those fields ([`applyfirst/saas/db.py:353-358`](../applyfirst/saas/db.py#L353-L358)). Identical inputs give the same letter, so nothing private crosses over.

### 6.5 How the Gmail pass is locked

**Why it matters.** The refresh token lets Agad send email as the person. Anyone who stole it could send email from their Gmail. So it is never stored in plain form.

**The idea, in everyday words.** Think of a lockbox inside a safe. Each pass goes into its own lockbox with a brand new key, called the data key. That key is then locked inside a safe opened by one master key, and the master key never enters the database. The person's user id is also stamped into the lockbox's seal. If someone moves the lockbox onto another person's row, the seal no longer matches and it will not open. The lock is AES-256-GCM, a standard cipher that also notices any changed byte.

```python
# applyfirst/saas/crypto.py:81-86
dek = AESGCM.generate_key(bit_length=256)
iv = os.urandom(_IV_LEN)
ciphertext = AESGCM(dek).encrypt(iv, plaintext, aad)

dek_iv = os.urandom(_IV_LEN)
encrypted_dek = dek_iv + AESGCM(master_key).encrypt(dek_iv, dek, None)
```

**Plain reading.** `generate_key` makes a new random key for every pass. `os.urandom` makes a fresh random starting value, so the same pass never locks to the same bytes twice. The last line locks the data key with the master key. The `aad` value is the owner stamp, and it is the user id ([`applyfirst/saas/db.py:287-288`](../applyfirst/saas/db.py#L287-L288)). When you look for how any secret is stored, find the `encrypt` call right before the database write.

- A stolen database file or backup cannot send any email, because the master key is not in it.
- Moving one person's locked pass onto another row fails. A test proves it ([`tests/test_saas_crypto.py:30`](../tests/test_saas_crypto.py#L30)).
- Anyone with a shell on the running server, meaning a command line typed straight into it, has both the file and the master key. Locking stored data does not stop that person.
- A wrong master key fails every unlock ([`applyfirst/saas/crypto.py:96-97`](../applyfirst/saas/crypto.py#L96-L97)), so every send fails quietly while `/health` stays green (section 6.10).

### 6.6 Cookies and CSRF

| Cookie | Holds | Lifetime | Set at |
|---|---|---|---|
| `applyfirst_session` | the user id | 7 days | [`applyfirst/saas/session.py:113-115`](../applyfirst/saas/session.py#L113-L115) |
| `applyfirst_oauth` | state, nonce, PKCE secret | 10 minutes | [`applyfirst/saas/session.py:130-134`](../applyfirst/saas/session.py#L130-L134) |
| `applyfirst_flash` | one code, `signed_in` or `gmail_connected` | 2 minutes | [`applyfirst/saas/session.py:150-155`](../applyfirst/saas/session.py#L150-L155) |

- Each cookie carries a seal made with the server secret, so any change is caught ([`applyfirst/saas/session.py:45-69`](../applyfirst/saas/session.py#L45-L69)).
- All three are HttpOnly, so page scripts cannot read them, and SameSite Lax, so other sites cannot make the browser send them with their own form posts ([`applyfirst/saas/session.py:95-104`](../applyfirst/saas/session.py#L95-L104)).
- In production each name gets the `__Host-` prefix, which locks the cookie to our exact site and to HTTPS ([`applyfirst/saas/session.py:83-84`](../applyfirst/saas/session.py#L83-L84)).

A CSRF attack is another website quietly making your browser press a button on our site. The defence is a secret token only our own pages know. It is the user id sealed with the server secret ([`applyfirst/saas/session.py:72-80`](../applyfirst/saas/session.py#L72-L80)), printed into every form as a hidden field ([`applyfirst/saas/templates/_ui.html:35-37`](../applyfirst/saas/templates/_ui.html#L35-L37)) and checked by `require_csrf`, which answers 403 on a mismatch ([`applyfirst/saas/app.py:292-305`](../applyfirst/saas/app.py#L292-L305)). Every action that changes something uses it. Log out, save profile, add and delete a word, Start and Disconnect Gmail ([`applyfirst/saas/app.py:430`](../applyfirst/saas/app.py#L430), [`applyfirst/saas/app.py:557`](../applyfirst/saas/app.py#L557), [`applyfirst/saas/app.py:586`](../applyfirst/saas/app.py#L586), [`applyfirst/saas/app.py:596`](../applyfirst/saas/app.py#L596), [`applyfirst/saas/app.py:623`](../applyfirst/saas/app.py#L623), [`applyfirst/saas/app.py:704`](../applyfirst/saas/app.py#L704)).

### 6.7 The CSP and the other safety headers

A CSP (Content Security Policy) is a rule list the browser obeys about where a page may load things from. One piece of middleware, code that wraps every reply on its way out, stamps it and three other headers on every page.

```python
# applyfirst/saas/app.py:226-232
resp.headers["X-Content-Type-Options"] = "nosniff"
resp.headers["X-Frame-Options"] = "DENY"
resp.headers["Referrer-Policy"] = "no-referrer"
resp.headers["Content-Security-Policy"] = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
```

| Rule | Plain meaning |
|---|---|
| `default-src 'self'` | Scripts, fonts and data load only from our own site, so no outside or inline script runs |
| `form-action 'self'` | Forms may only submit to our own site. This is why the Google button is a link |
| `frame-ancestors 'none'`, `DENY` | No other site may show our pages in a frame, which blocks trick clicks |
| `nosniff` | The browser must trust the file type we state and never guess |
| `no-referrer` | Other sites are not told which of our pages a person came from |

The CSP is frozen by your decision, and the tests pin its exact text in `tests/_saas_client.py`. Getting paid will need one deliberate change to `form-action` (section 11.5).

### 6.8 Rate limits

1. Only addresses starting with `/auth/` are counted ([`applyfirst/saas/app.py:239`](../applyfirst/saas/app.py#L239)).
2. The visitor's address comes from a label added by the proxy, the front-door server that passes visitors in. That is `fly-client-ip` on Fly, or the last `X-Forwarded-For` entry behind Caddy, never the first entry, which a visitor could fake ([`applyfirst/saas/app.py:187-207`](../applyfirst/saas/app.py#L187-L207)).
3. The count lives in the database, so all web processes share one count ([`applyfirst/saas/db.py:726-748`](../applyfirst/saas/db.py#L726-L748)).
4. The default is 20 hits per address per 60 seconds ([`applyfirst/saas/config.py:171-172`](../applyfirst/saas/config.py#L171-L172)). Over it the answer is 429, "slow down" ([`applyfirst/saas/app.py:251-253`](../applyfirst/saas/app.py#L251-L253)).
5. If the counter's database fails, the answer is 503, so the limiter fails closed instead of waving everyone through ([`applyfirst/saas/app.py:244-248`](../applyfirst/saas/app.py#L244-L248)).

Nothing else is rate-limited. Forms, the preview and `/health` are open to as many requests as anyone sends ([`docs/OPERATIONS.md:334-335`](../docs/OPERATIONS.md#L334-L335)).

### 6.9 Privacy promises against the code

The privacy page is `applyfirst/saas/templates/privacy.html`, and a test freezes its wording ([`tests/test_saas_legal_text.py:27`](../tests/test_saas_legal_text.py#L27)).

| Promise on the page | What the code does | Verdict |
|---|---|---|
| Only the send permission, never read your mail ([`applyfirst/saas/templates/privacy.html:43-48`](../applyfirst/saas/templates/privacy.html#L43-L48)) | Asks for name and email, then `gmail.send` only ([`applyfirst/saas/google_oauth.py:32-33`](../applyfirst/saas/google_oauth.py#L32-L33)) | Kept |
| Letters go only to you ([`applyfirst/saas/templates/privacy.html:43-46`](../applyfirst/saas/templates/privacy.html#L43-L46)) | From and To are both your address ([`applyfirst/saas/gmail_send.py:75-76`](../applyfirst/saas/gmail_send.py#L75-L76)) | Kept |
| The Gmail pass is encrypted at rest ([`applyfirst/saas/templates/privacy.html:30-32`](../applyfirst/saas/templates/privacy.html#L30-L32)) | Section 6.5 | Kept |
| Tokens and message contents are never logged ([`applyfirst/saas/templates/privacy.html:38-39`](../applyfirst/saas/templates/privacy.html#L38-L39)) | Log events carry ids and words, never passes or letters ([`applyfirst/saas/worker.py:302-305`](../applyfirst/saas/worker.py#L302-L305)) | Kept, as far as the code shows |
| Disconnect cancels the pass at Google and deletes it ([`applyfirst/saas/templates/privacy.html:78-79`](../applyfirst/saas/templates/privacy.html#L78-L79)) | [`applyfirst/saas/app.py:704-716`](../applyfirst/saas/app.py#L704-L716) | Kept |
| Your data is never used to train AI ([`applyfirst/saas/templates/privacy.html:65-66`](../applyfirst/saas/templates/privacy.html#L65-L66)) | The code cannot enforce it. It depends on Gemini billing being on (section 9.3) | Depends on you |
| Delete your account by emailing us ([`applyfirst/saas/templates/privacy.html:79-81`](../applyfirst/saas/templates/privacy.html#L79-L81)) | No route, script or tool deletes a person | **Not built** |
| "We keep your data while your account is active" ([`applyfirst/saas/templates/privacy.html:78`](../applyfirst/saas/templates/privacy.html#L78)) | There is no idea of an inactive account. Alerts and usage rows are never pruned | Partly |
| Not mentioned | Seven daily backups, sign-in addresses for two minutes, host logs | Missing from the page |

A deletion today would mean hand-typed SQL, the database's own command language, on the live file. The links from a person to their other rows all say "delete with the parent" ([`applyfirst/saas/db.py:168`](../applyfirst/saas/db.py#L168), [`applyfirst/saas/db.py:460`](../applyfirst/saas/db.py#L460)), but that rule only works when `foreign_keys` is on. The app switches it on ([`applyfirst/saas/db.py:109`](../applyfirst/saas/db.py#L109)), while the plain `sqlite3` tool does not ([`docs/OPERATIONS.md:319-321`](../docs/OPERATIONS.md#L319-L321)).

### 6.10 Honest gaps

1. **Account deletion is promised and not built** (section 6.9).
2. **A wrong master key breaks every send while `/health` stays green.** Each unlock fails inside its alert ([`applyfirst/saas/worker.py:182`](../applyfirst/saas/worker.py#L182)), the safety net marks it failed ([`applyfirst/saas/worker.py:292-295`](../applyfirst/saas/worker.py#L292-L295)), and `/health` only reads the three notes about searching and AI ([`applyfirst/saas/app.py:476-478`](../applyfirst/saas/app.py#L476-L478)).
3. **The "no AI training" promise depends on Gemini billing**, which is off today (section 9.3).
4. **The 429 and 503 replies from the rate limiter carry no safety headers.** The limiter was added second, which makes it the outer layer, so its early replies skip the header stamp ([`applyfirst/saas/app.py:223-254`](../applyfirst/saas/app.py#L223-L254)). They are one line of plain text, so the harm is small.
5. **Log out cannot cancel a copied cookie**, because there is no list of live sessions (section 4.7).
6. **Watch words are case-sensitive**, so "Shopify" and "shopify" are two words and two searches ([`applyfirst/saas/db.py:201`](../applyfirst/saas/db.py#L201)).
7. **Only `/auth/` is rate-limited** (section 6.8).
8. **Backups share the database's disk on Fly** (section 3.7).

---

## 7. Keeping it healthy

**In short.** Agad watches itself in four ways, a health page, alerts to you, a watchdog that restarts a stuck worker and a blind detector for when onlinejobs.ph stops answering. None of it reaches you unless an outside uptime monitor watches `/health`, which is the one thing you must set up.

### 7.1 Two health pages

- **`/healthz`** always answers "ok" while the web app is up ([`applyfirst/saas/app.py:455-457`](../applyfirst/saas/app.py#L455-L457)). Fly's own check uses it ([`fly.toml:63-68`](../fly.toml#L63-L68)).
- **`/health`** is for your outside monitor ([`applyfirst/saas/app.py:459-515`](../applyfirst/saas/app.py#L459-L515)). It reads the worker's notes and answers 503, meaning "not healthy", in these cases.

| Field | Value | When | Answer |
|---|---|---|---|
| `worker` | `starting` | No round yet, web up less than 2.5 intervals | 200 |
| `worker` | `ok` | Last round within 2.5 intervals | 200 |
| `worker` | `never_ran` | No round yet, web up longer than 2.5 intervals | 503 |
| `worker` | `stale` | Last round older than 2.5 intervals | 503 |
| `polling` | `blind` | 3 or more blind rounds in a row | 503 |
| `ai` | `off` | Production, no Gemini credential, not switched off on purpose | 503 |

The 2.5 factor is at [`applyfirst/saas/app.py:184`](../applyfirst/saas/app.py#L184), the states are worked out at [`applyfirst/saas/app.py:483-507`](../applyfirst/saas/app.py#L483-L507), and the final answer is at [`applyfirst/saas/app.py:508`](../applyfirst/saas/app.py#L508).

What `/health` cannot see. Failed sends and a wrong master key leave it green (section 6.10), and so does a suspended Google sign-in app, which fails every sign-in ([`docs/OPERATIONS.md:324-325`](../docs/OPERATIONS.md#L324-L325)). So also read the `cycle_complete` log line now and then, whose `failed` count shows them ([`applyfirst/saas/worker.py:302-305`](../applyfirst/saas/worker.py#L302-L305)).

### 7.2 Alerts to you

These go to **you**, never to users.

1. A webhook first, meaning a secret Slack or Discord address ([`applyfirst/saas/notify.py:31-47`](../applyfirst/saas/notify.py#L31-L47)).
2. Then email through the server's own mail account ([`applyfirst/saas/notify.py:49-56`](../applyfirst/saas/notify.py#L49-L56)).
3. If neither works, a CRITICAL log line, and the worker carries on ([`applyfirst/saas/notify.py:58-60`](../applyfirst/saas/notify.py#L58-L60)).

Each kind of alert goes out at most once every 6 hours, and one that no channel accepted is tried again after 15 minutes ([`applyfirst/saas/worker.py:54-55`](../applyfirst/saas/worker.py#L54-L55), [`applyfirst/saas/worker.py:416-432`](../applyfirst/saas/worker.py#L416-L432)).

| Alert | Why | Where |
|---|---|---|
| Agad worker cannot start | No master key | [`applyfirst/saas/worker.py:590-592`](../applyfirst/saas/worker.py#L590-L592) |
| AI not configured | Production without a Gemini credential | [`applyfirst/saas/worker.py:468-478`](../applyfirst/saas/worker.py#L468-L478) |
| AI calls are failing | Every AI call fell back, two rounds running | [`applyfirst/saas/worker.py:364-384`](../applyfirst/saas/worker.py#L364-L384) |
| Agad worker is blind | 3 rounds in a row with no answer from onlinejobs.ph | [`applyfirst/saas/worker.py:435-442`](../applyfirst/saas/worker.py#L435-L442) |
| Backup failed | The daily copy did not work | [`applyfirst/saas/worker.py:495-501`](../applyfirst/saas/worker.py#L495-L501) |
| Reconnect email trouble | Users cannot be told their Gmail ended | [`applyfirst/saas/worker.py:316-357`](../applyfirst/saas/worker.py#L316-L357) |

After a deploy, run `python -m applyfirst.saas.notify --test`. It names the channel that really delivered ([`applyfirst/saas/notify.py:63-90`](../applyfirst/saas/notify.py#L63-L90)).

### 7.3 The watchdog and the restart loop

A watchdog is a timer that ends a program that has stopped making progress, so something else can start a fresh copy.

1. It is armed only while a round runs, so the long nap never counts ([`applyfirst/saas/worker.py:558-569`](../applyfirst/saas/worker.py#L558-L569)).
2. The round "beats" after every job on a results page, every word (even a failed one), every alert and every reconnect email ([`applyfirst/saas/worker.py:273`](../applyfirst/saas/worker.py#L273), [`applyfirst/saas/worker.py:281`](../applyfirst/saas/worker.py#L281), [`applyfirst/saas/worker.py:298`](../applyfirst/saas/worker.py#L298), [`applyfirst/saas/reconnect.py:297`](../applyfirst/saas/reconnect.py#L297)).
3. After 900 seconds with no beat, it logs `worker_stalled` and ends the worker with exit code 70, a number a program leaves behind to say why it stopped ([`applyfirst/saas/worker.py:534-544`](../applyfirst/saas/worker.py#L534-L544)). It must use a hard exit, because a program stuck waiting on the network cannot be interrupted any other way.
4. On Fly the restart loop starts a fresh worker (section 3.2). On Oracle systemd does it after 10 seconds ([`deploy/oracle/applyfirst-saas-worker.service:21-22`](../deploy/oracle/applyfirst-saas-worker.service#L21-L22)).

So a hung worker now costs about 15 minutes, not a night.

### 7.4 Blind detection

A dead-man's switch raises the alarm when an expected signal stops. Here the signal is "jobs keep coming back from onlinejobs.ph".

1. If at least one word was searched and zero jobs came back in total, the worker searches "virtual assistant", a term that always has posts ([`applyfirst/saas/worker.py:283-286`](../applyfirst/saas/worker.py#L283-L286), [`applyfirst/saas/worker.py:64`](../applyfirst/saas/worker.py#L64)). That is the canary. A canary is a test you trust to always work, so its failure means the problem is on the other side.
2. A round is blind only if the canary also fails ([`applyfirst/saas/worker.py:405`](../applyfirst/saas/worker.py#L405)). One person watching a word with no posts never counts.
3. At 3 blind rounds in a row ([`applyfirst/saas/config.py:188`](../applyfirst/saas/config.py#L188)) it alerts you and `/health` turns 503.

One blind spot remains. A page that still parses, like a captcha that happens to yield one job link, keeps the switch quiet ([`docs/OPERATIONS.md:328-329`](../docs/OPERATIONS.md#L328-L329)).

### 7.5 AI health

A wrong, revoked or unpaid Gemini credential looks like "AI on" from outside, because letters still go out as the person's own message. So the worker counts, each round, how many fresh AI tries fell back ([`applyfirst/saas/worker.py:165`](../applyfirst/saas/worker.py#L165)). If every try failed two rounds running, it alerts you ([`applyfirst/saas/worker.py:364-384`](../applyfirst/saas/worker.py#L364-L384)).

### 7.6 Logs

Both programs write one JSON line per event to the error stream. JSON is a plain text format for data that people and programs can both read ([`applyfirst/log.py:50-60`](../applyfirst/log.py#L50-L60)). On Fly you read them with `fly logs`, and on Oracle systemd's journal keeps them.

| Event | Means |
|---|---|
| `cycle_complete` | One round finished, with counts of words, jobs, alerts, sent, failed, capped and skipped |
| `search_failed` | One word's search failed this round |
| `detail_fetch_failed` | A job's full page failed, the short blurb was kept |
| `worker_blind` | 3 blind rounds in a row |
| `worker_stalled` | The watchdog ended a hung round |
| `worker_cycle_crashed` | A round crashed, the loop carried on |
| `ai_call_failed`, `ai_all_failed` | One AI try failed, or every try in a round failed |
| `backup_failed` | The daily copy failed |
| `signin_failed` | A Google sign-in did not finish, with the reason |

### 7.7 What to watch in the first weeks after launch

1. **Round length against the interval.** Compare the time between `cycle_complete` lines with the 10 minutes the pages promise. The operations doc expects rounds to overrun at about 185 distinct words ([`docs/OPERATIONS.md:286-289`](../docs/OPERATIONS.md#L286-L289)).
2. **The `failed` count in `cycle_complete`.** It is the only sign of send trouble.
3. **`search_failed` and `detail_fetch_failed`.** A rising number is the first hint of a block.
4. **Gemini spending**, in Google's billing page, against your spend cap (section 9.3).
5. **Disk use on the volume.** Old jobs and alerts are never deleted (section 3.6).
6. **One backup copied off the machine each week**, until the off-machine copy is automatic.

### 7.8 The one monitor you must not skip

Point an outside uptime monitor, such as UptimeRobot, at `/health`. It is the only thing that turns a stale, hung or blind worker, or a missing AI credential, into a message that wakes you. With no webhook set, it is your only pager at all. The alternatives, like healthchecks.io's free plan with 20 checks, work the same way ([Healthchecks pricing](https://healthchecks.io/pricing/)).

---

## 8. The code base tour

**In short.** V2 lives in `applyfirst/saas/`, V1 and the shared pieces live in the rest of `applyfirst/`, and `tests/` holds 1,391 tests. Those tests and one smoke script are the only quality gates, because the project has no linter or type checker, the tools that scan code for mistakes without running it.

### 8.1 Folder by folder

**The repo root.**

- `Handoff.md` is the running project diary and the first thing a new session reads.
- `DESIGN-HANDOFF.md` is the brief to paste into a fresh design session.
- `Dockerfile`, `fly.toml` and `entrypoint.sh` are the Fly.io beta (section 3.2).
- `requirements.txt` and `requirements-dev.txt` list the Python packages, without pinned versions.
- `.gitattributes` keeps shell scripts and vendored files byte for byte the same on Windows and Linux. Vendored means a copy of someone else's code kept inside our project.

**`applyfirst/saas/`, the public service.**

| File | What it is |
|---|---|
| `app.py` | The web app. Every route, the safety headers and the sign-in rate limit |
| `db.py` | All the data code and the table layout |
| `worker.py` | The search, fan-out and send loop, plus the watchdog and the daily backup |
| `google_oauth.py` | Google sign-in and Connect Gmail, including the ID card checks |
| `gmail_send.py` | Sends one email from a person to themselves through the Gmail API |
| `crypto.py` | The Gmail pass lock (section 6.5) |
| `session.py` | Signed cookies, CSRF tokens and the one-shot note |
| `reconnect.py` | Emails a person once when Google ends their Gmail connection |
| `notify.py` | Owner alerts by webhook, then email, then log |
| `onboarding.py` | Works out the next sign-up step from what is saved |
| `preview.py` | Builds the sample letter for Step 4 |
| `config.py` | Reads every setting and refuses unsafe combinations |
| `tenant.py` | The per-person filter helper |
| `backup.py` | The backup entry point, with an optional off-machine copy |
| `static_assets.py` | Serves style files and scripts with a content fingerprint and long caching |
| `templates/` | The pages |
| `static/` | Style files, scripts, fonts, brand images, licences, and vendored copies of Basecoat, a small ready-made style kit, and of a confetti script |

**The rest of `applyfirst/`, V1 and the shared pieces.**

- `cli.py`, `pipeline.py`, `detector.py`, `store.py`, `config.py`, `health.py` and `pdf.py` are V1 only.
- `models.py` (the shape of a job), `profile.py` (the shape of a person's details) and `screening.py` (spots an employer's questions) are small shared helpers.
- `sources/` reads onlinejobs.ph. Shared.
- `tailor/` writes letters. `engine.py` runs it, `prompt.py` holds the AI instructions, `llm.py` calls Gemini and `contract.py` is the answer's shape. Shared.
- `notify/compose.py` lays out the application email. Shared.
- `notify/email_smtp.py` sends by SMTP, for V1's letters and V2's owner-alert fallback.
- `backup.py` and `log.py` are shared.
- `web/` is V1's private read-only dashboard.

**The other folders.**

- `tests/` holds 56 test files, three helper files, two saved onlinejobs.ph pages and saved copies of the legal page wording.
- `tools/` rebuilds the trimmed Basecoat and the Inter font subset.
- `deploy/oracle/` is the Oracle runbook, unit files, Caddyfile and settings template (section 3.3).
- `docs/` holds this guide, `SYSTEM-DESIGN.md`, `OPERATIONS.md` (every production command), `LOCAL-TEST.md` (running V2 on your PC), `legal/google-verification.md` (the Google runbook) and the finished milestone plans.
- **Local only, not in git.** `.venv/`, `.noxa/` (the smoke script and the preview runner), the two database files, `backups/`, `profile.yaml` and `REMOTE.md`.

### 8.2 What V1 and V2 share

They never share a database file, but V2 reuses five of V1's pieces.

The proof, one link per shared piece. The worker builds V1's job reader ([`applyfirst/saas/worker.py:599-603`](../applyfirst/saas/worker.py#L599-L603)) and V1's letter engine ([`applyfirst/saas/worker.py:83-88`](../applyfirst/saas/worker.py#L83-L88)), and lays out each email with V1's email code ([`applyfirst/saas/worker.py:42`](../applyfirst/saas/worker.py#L42)). V2's backup calls the shared core ([`applyfirst/saas/backup.py:19`](../applyfirst/saas/backup.py#L19)). Owner alerts by email reuse V1's SMTP sender ([`applyfirst/saas/notify.py:51-52`](../applyfirst/saas/notify.py#L51-L52)).

**Why it matters.** A change in `applyfirst/tailor/` or `applyfirst/sources/` changes your own letters and every user's letters at once. When the AI instructions change, their fingerprint changes and V2 wipes its saved letters once ([`applyfirst/tailor/prompt.py:112`](../applyfirst/tailor/prompt.py#L112), [`applyfirst/saas/worker.py:91-106`](../applyfirst/saas/worker.py#L91-L106)).

### 8.3 The front end in layers

The pages are HTML templates filled in on the server by Jinja, a template engine that swaps placeholders for real values. They live in `applyfirst/saas/templates/`. `base.html` is the frame every page extends, and `_ui.html` holds the shared pieces and the owner switches at the top, such as `INVITE_ONLY` ([`applyfirst/saas/templates/_ui.html:8`](../applyfirst/saas/templates/_ui.html#L8)) and `CELEBRATE` ([`applyfirst/saas/templates/_ui.html:22`](../applyfirst/saas/templates/_ui.html#L22)).

**How a page's head is built.** `base.html` loads files in a fixed order, with empty slots each page may fill ([`applyfirst/saas/templates/base.html:12-19`](../applyfirst/saas/templates/base.html#L12-L19)). `static_url()` adds a short fingerprint of a file's content to its address, so a browser can keep the file for a year and still fetch a new one the moment it changes ([`applyfirst/saas/static_assets.py:30-50`](../applyfirst/saas/static_assets.py#L30-L50), [`applyfirst/saas/static_assets.py:77-84`](../applyfirst/saas/static_assets.py#L77-L84)).

**CSS layers.** CSS is the language of style rules, the colours, sizes and spacing. Think of its layers as floors in a building. A rule on a higher floor always wins over a rule on a lower floor. `app.css` names the first seven floors, lowest first ([`applyfirst/saas/static/css/app.css:6`](../applyfirst/saas/static/css/app.css#L6)). `motion.css`, `hero.css` and `story.css` each add their own floor on top ([`applyfirst/saas/static/css/motion.css:2`](../applyfirst/saas/static/css/motion.css#L2), [`applyfirst/saas/static/css/hero.css:14`](../applyfirst/saas/static/css/hero.css#L14), [`applyfirst/saas/static/css/story.css:25`](../applyfirst/saas/static/css/story.css#L25)).

```mermaid
flowchart BT
    basecoat["basecoat<br/>trimmed shadcn-style parts"]
    reset["reset<br/>app.css"]
    tokens["tokens<br/>app.css colours and sizes"]
    base["base<br/>app.css body and type"]
    components["components<br/>app.css buttons, cards, alerts"]
    screens["screens<br/>app.css page layouts"]
    journey["journey<br/>journey.css sign-up look, dark mode"]
    motion["motion<br/>motion.css frozen animations"]
    hero["hero<br/>hero.css, homepage only"]
    story["story<br/>story.css, homepage only"]
    basecoat --> reset --> tokens --> base --> components --> screens --> journey --> motion
    screens --> hero --> story
```

Read the arrows as "sits under". The straight column is the stack on the sign-up pages and the dashboard. The side branch is the homepage.

| Page | Basecoat and journey look | Motion files | Homepage hero files | Follows phone dark mode |
|---|---|---|---|---|
| Homepage | no | no | yes | no |
| Login, Sign-in didn't finish | yes | no | no | yes |
| Four onboarding steps, Dashboard | yes | yes | no | yes |
| Privacy, Terms | no | no | no | no |

- **Scripts only add polish.** Every page works with JavaScript off. `app.js` does copy buttons and busy states, `reveal.js` fades sections in, `vt.js` and `motion.js` run the sign-up animations, and `scene.js` draws the homepage background with its pause button.
- **Fonts.** The homepage and legal pages use the device's own font and download nothing ([`applyfirst/saas/static/css/app.css:52`](../applyfirst/saas/static/css/app.css#L52)). The sign-up pages use a self-hosted 28 KB Inter on Android and Windows ([`applyfirst/saas/static/css/journey.css:7-12`](../applyfirst/saas/static/css/journey.css#L7-L12)). Apple devices should never download it, because their own system font is first in the list ([`applyfirst/saas/static/css/journey.css:38`](../applyfirst/saas/static/css/journey.css#L38)). That has not yet been checked on a real iPhone.
- **Frozen files.** `motion.css`, `vt.js` and `motion.js` are each within about a hundred compressed bytes of a size limit their tests set ([`tests/test_saas_motion.py:358-365`](../tests/test_saas_motion.py#L358-L365)). New work goes in new files.
- **No purple.** A test rejects any colour at hue 230 to 345 anywhere, vendored files included ([`tests/test_saas_palette.py:227`](../tests/test_saas_palette.py#L227)).

### 8.4 Tests and gates

| Area | Tests | Main files |
|---|---|---|
| Look, motion and asset guards | 686 | `test_saas_journey.py`, `test_saas_motion.py`, `test_saas_palette.py` |
| Pages and the sign-up flow | 303 | `test_saas_flash.py`, `test_saas_profile_errors.py`, `test_saas_signin_failed.py` |
| Worker and operations | 186 | `test_saas_ops.py`, `test_saas_reconnect.py`, `test_saas_worker.py` |
| Security and data | 137 | `test_saas_gmail_scope.py`, `test_saas_cross_tenant.py`, `test_saas_crypto.py` |
| Shared code and V1 | 79 | `test_tailor_prompt.py` and the V1 tests |

That is 1,391 tests in 56 files, all passing in about two and a half minutes on your PC, measured on 27 September 2026. Run them from the repo root in PowerShell.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe .noxa\redesign-saas-ui\inputs\preserve_smoke.py
```

The first line runs every test. The second is the smoke script, 607 checks, 0 failed. It draws every page in every state, submits every form exactly as the HTML defines it and scans everything for anything the CSP would block. It exists because the unit tests send the CSRF token as a header, so a page that lost its hidden token field would still pass them while breaking every real browser ([`.noxa/redesign-saas-ui/inputs/preserve_smoke.py:1-24`](../.noxa/redesign-saas-ui/inputs/preserve_smoke.py#L1-L24)). Run it before and after any template or style change. It is git-ignored, so it lives only on your PC. Back it up.

What the guard tests protect, a few examples. A stranger gets "not found" on someone else's data ([`tests/test_saas_cross_tenant.py:37`](../tests/test_saas_cross_tenant.py#L37)). The Gmail lock refuses a wrong key and any tampering ([`tests/test_saas_crypto.py:13-80`](../tests/test_saas_crypto.py#L13-L80)). Every sentence of the legal pages still renders ([`tests/test_saas_legal_text.py:27`](../tests/test_saas_legal_text.py#L27)). A missing AI key is loud, a hung worker is restarted and a backup never leaves a half file ([`tests/test_saas_ops.py:1-15`](../tests/test_saas_ops.py#L1-L15)).

---

## 9. What to expect

**In short.** The biggest risks are not in the code. onlinejobs.ph's terms forbid automated use without permission, Google caps the beta at 100 users with weekly disconnects, and Gemini's model and free-tier rules both need action before real users arrive. They are listed here most important first.

### 9.1 onlinejobs.ph terms clause 7.4, and the 5-second crawl delay

**The terms.** Clause 7.4 of the onlinejobs.ph terms says "You are only permitted to use the Service personally and agree to do so without the use of any automated means including but not limited to the use of robotic tools except where permission has been expressly granted by OnlineJobs" ([onlinejobs.ph terms](https://www.onlinejobs.ph/terms)). Clause 10.3 lets them end your use of the service for a breach (same page). Agad's whole engine is automated reading of their site, and nothing grants permission.

**robots.txt.** The site's robots.txt, a file where a site tells robots its rules, lets any robot read the job pages but asks it to wait 5 seconds between requests with `Crawl-delay: 5` ([robots.txt](https://www.onlinejobs.ph/robots.txt)). The search page is not blocked.

**What the code does today.**

- It waits only 1.0 to 2.5 seconds between searches and 0.3 to 0.8 seconds after each job page ([`applyfirst/saas/worker.py:57-58`](../applyfirst/saas/worker.py#L57-L58)). That is faster than the site asks.
- It calls itself a normal Chrome browser ([`applyfirst/sources/base.py:18-21`](../applyfirst/sources/base.py#L18-L21)). That hides that Agad is a robot. It may delay a block, but it looks worse if the site owner notices.

**What it means.** If onlinejobs.ph blocks Agad's one address, every user stops getting jobs at the same moment. The site sits behind Cloudflare, which scores every request for how robotic it looks ([Cloudflare bot score](https://developers.cloudflare.com/bots/concepts/bot-score/)). Whether the site has bot blocking switched on is **UNVERIFIED**. Whether the terms bind a visitor who never signed up is a legal question, **UNVERIFIED**, ask a lawyer. No public API or job feed was found, which is also **UNVERIFIED**. Rotating addresses to dodge a block would be deliberately evading the owner's decision, and this guide does not recommend it.

**What to do.**

1. Email onlinejobs.ph, explain Agad (it reads public listings once per word for all users, never applies for anyone, and sends people back to their site) and ask for written permission or a feed.
2. Put one shared speed limit of one request every 5 seconds on everything that touches the site.
3. Use an honest browser name with a contact address, like `AgadBot/1.0 (+https://your-domain/bot)`.
4. Re-read robots.txt every day, which the robots standard recommends ([RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html)).
5. Never show their logo, and add "Agad is not affiliated with OnlineJobs.ph" to the footer.

### 9.2 Google verification, the 100-user Testing cap and the 7-day expiry

Your Google project is in Testing mode today.

- **100 users at most.** Testing mode is "limited to up to 100 test users" ([Google Cloud help](https://support.google.com/cloud/answer/15549945)).
- **Every Gmail connection dies after 7 days.** "Authorizations by a test user will expire seven days from the time of consent", refresh token included (same page). That is why the reconnect email exists (section 5.10).
- **`INVITE_ONLY` is page wording, not a gate.** It is a template switch ([`applyfirst/saas/templates/_ui.html:8`](../applyfirst/saas/templates/_ui.html#L8)), and `/auth/login` has no invite check ([`applyfirst/saas/app.py:386-397`](../applyfirst/saas/app.py#L386-L397)). The real gate today is Google's hand-made test-user list.

**The way out is verification.** A scope is one permission an app asks Google for. `gmail.send` is a "sensitive" scope, not a "restricted" one ([Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)). That means Google's own review and **no paid CASA security audit**, which applies only to restricted scopes ([restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)). Never add `gmail.compose` or `gmail.insert`, which are restricted.

1. **Brand check.** A public homepage and a privacy policy on a domain you own, proven in Google Search Console. It takes a few minutes, or 2 to 3 business days if a person looks, and a pass is valid for 7 days ([brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)). Whether a `fly.dev` address could pass is **UNVERIFIED**, so buy a real domain.
2. **Scope review.** A written reason for `gmail.send`, and a demo video of the whole sign-in and the features that use it. It "typically takes 3-5 business days" ([sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification), [demo video](https://support.google.com/cloud/answer/13804565)). A ready-to-paste reason is in `docs/legal/google-verification.md`. Plan for 1 to 3 weeks with back-and-forth, which is an estimate.
3. **The gap in between.** From the moment you publish until approval, people see an "unverified app" warning and the app is capped at 100 new users in total ([unverified apps](https://support.google.com/cloud/answer/7454865)).

Even after verification a Gmail connection can still end when a person changes their Google password, revokes access or leaves it unused for six months ([OAuth overview](https://developers.google.com/identity/protocols/oauth2)). So the reconnect email stays useful after launch.

### 9.3 Gemini, the model change and the free tier training rule

**The model is being fenced off.** The code uses `gemini-2.5-flash` unless told otherwise ([`applyfirst/saas/config.py:161`](../applyfirst/saas/config.py#L161)). Since 18 September 2026 Google limits access to the 2.5 models "to users who have actively used them in the past" and points new projects to 3.5 Flash-Lite or 3.8 Flash ([changelog](https://ai.google.dev/gemini-api/docs/changelog), [2.5 Flash page](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)). No shutdown date is announced. Whether a new Google project for production counts as a past user is **UNVERIFIED**. Gemini 3.5 Flash-Lite costs the same, USD 0.30 per million input tokens and USD 2.50 per million output tokens ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)), so test it and switch `GEMINI_MODEL` when it reads well.

**The free tier breaks your privacy promise.** On the free tier Google uses content "to provide, improve, and develop Google products and services and machine learning technologies", people may read it, and Google says "Do not submit sensitive, confidential, or personal information to the Unpaid Services". The paid tier is not used to improve Google's products ([Gemini API terms](https://ai.google.dev/gemini-api/terms)). Agad sends names and application text, and the privacy page promises no training ([`applyfirst/saas/templates/privacy.html:65-66`](../applyfirst/saas/templates/privacy.html#L65-L66)). So turn on billing before any real user's data flows. The deploy file already warns about it ([`fly.toml:16-19`](../fly.toml#L16-L19)).

**Thinking is unlimited.** The request sets only the answer format and a temperature, the setting for how adventurous the wording is ([`applyfirst/tailor/llm.py:37`](../applyfirst/tailor/llm.py#L37)). Gemini 2.5 Flash thinks by default, and thinking is billed as output ([thinking docs](https://ai.google.dev/gemini-api/docs/thinking)). A cover letter needs little reasoning, so turning thinking down is the cheapest saving there is.

**Spending caps.** A billing account's first tier has a USD 250 monthly cap. When a cap is reached, the service pauses for every linked project "until the start of the next billing cycle" ([rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [billing](https://ai.google.dev/gemini-api/docs/billing)). That would stop every letter at once, so move up a tier before you need it.

### 9.4 One machine, because SQLite lives on one volume

A Fly volume attaches to one machine only, and Fly does not copy it ([Fly volumes](https://docs.fly.io/volumes/overview/)). SQLite's WAL mode also needs every program using the file on the same computer ([SQLite WAL](https://www.sqlite.org/wal.html)). So the web app and the worker must share one machine ([`fly.toml:3-5`](../fly.toml#L3-L5)), and one machine going down takes all of Agad down. SQLite's speed is not the problem. SQLite says sites under 100,000 hits a day "should work fine" ([When to use SQLite](https://www.sqlite.org/whentouse.html)), and the operations doc measured about 595 single-row writes per second ([`docs/OPERATIONS.md:311-312`](../docs/OPERATIONS.md#L311-L312)).

### 9.5 Gmail limits

- A personal Gmail can send about 500 emails a day, and recovers within 1 to 24 hours if it trips ([Gmail Help](https://support.google.com/mail/answer/22839?hl=en)). Agad sends at most 10 per person per day, so this only bites someone who already sends hundreds of emails a day.
- The Gmail API is free today. Google plans charges above 80,000,000 quota units per project per day "later in 2026", with at least 90 days' notice ([Gmail API quota](https://developers.google.com/workspace/gmail/api/reference/quota)). One send is 100 units, so 10,000 users at 10 a day would use about one eighth of that line.

### 9.6 Costs per user, and the margin at PHP 199

PHP 199 is about USD 3.18. The estimates below use the Gemini prices above and **UNVERIFIED** assumptions of about 4,000 input tokens, 600 output tokens and 1,500 thinking tokens per letter, and 3 letters a day for a typical user.

| Per user per month | Thinking turned down | Thinking at default |
|---|---|---|
| Gemini, 3 letters a day | USD 0.24, PHP 15 | USD 0.59, PHP 37 |
| Gemini, 10 a day (the cap) | USD 0.81, PHP 51 | USD 1.95, PHP 122 |
| Hosting at 100 users | USD 0.04, PHP 3 | USD 0.04, PHP 3 |
| PayMongo fee, GCash | PHP 5 | PHP 5 |
| PayMongo fee, card | PHP 22 | PHP 22 |

| What is left from PHP 199 | Thinking turned down | Thinking at default |
|---|---|---|
| Typical user, GCash | about PHP 176 | about PHP 154 |
| Heavy user at the cap, GCash | about PHP 140 | about PHP 69 |
| Heavy user at the cap, card | about PHP 123 | about PHP 52 |

These are before income tax. The margin holds in every case, but a heavy user with thinking left on eats most of it. Keep the daily cap, turn thinking down and watch real usage. Nothing today caps total spending across all users ([`docs/OPERATIONS.md:273-274`](../docs/OPERATIONS.md#L273-L274)), so also set your own spend cap in Google's billing page. Sources are [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Fly pricing](https://docs.fly.io/about/pricing/) and [PayMongo pricing](https://www.paymongo.com/pricing).

### 9.7 Smaller things to expect

- **The disk fills in about a year**, because old jobs and alerts are never deleted (section 3.6). Backups also refuse when free disk is under twice the database, so they stop first.
- **A person who starts without Gmail gets nothing, silently**, and those jobs are never re-sent (section 5.11).
- **The library versions are not pinned**, so a rebuild can pull a new major version and break things with no code change ([`docs/OPERATIONS.md:332-333`](../docs/OPERATIONS.md#L332-L333)).
- **The homepage has never been looked at by a person on a real phone**, according to the handoff.

---

## 10. Scaling when traffic grows

**In short.** The first wall is Google's 100-user cap, not servers. After that the limit that matters is onlinejobs.ph's 5-second crawl delay, which no amount of machines can raise, so the real fix is to read the site's newest-jobs list once for everyone instead of searching once per watch word.

### 10.1 The one limit no server can raise

At one request every 5 seconds, Agad may make 12 requests a minute, 120 every 10 minutes and 17,280 a day, for the whole app and every user combined. More machines or parallel workers do not raise it, because the limit is on the site's side. Ten workers each waiting 5 seconds would still be ten times too fast. Only onlinejobs.ph can raise it, by giving permission or a feed.

Today the worker searches once per distinct watch word ([`applyfirst/saas/db.py:598-609`](../applyfirst/saas/db.py#L598-L609)), one after another ([`applyfirst/saas/worker.py:256-263`](../applyfirst/saas/worker.py#L256-L263)), and each person may save 20 words ([`applyfirst/saas/app.py:69`](../applyfirst/saas/app.py#L69)). So 100 people could mean anywhere from about 100 to 2,000 searches a round. Honouring 5 seconds fits only about 100 searches in 10 minutes. Past that a round takes longer than 10 minutes, and because the sleep starts after the round ([`applyfirst/saas/worker.py:619-620`](../applyfirst/saas/worker.py#L619-L620)), the promise of "about every 10 minutes" breaks with no warning.

### 10.2 How each part grows

| Part | Grows with | Hard limit | Cost growth |
|---|---|---|---|
| Reading onlinejobs.ph | Distinct words today, jobs posted with the newest-list design | 1 request per 5 s, for the whole app | About zero, incoming data is free |
| Writing letters (Gemini) | Letters sent | Your tier's monthly cap | The main cost, roughly in step with letters |
| Sending (Gmail API) | Letters sent | 500 a day per personal Gmail | Free today |
| Website | Visitors | One machine while on SQLite | Small |
| Database | Rows and connections | One machine while on SQLite | USD 25 to 75 once on Postgres |

### 10.3 Stage A, about 100 users (now)

- **What breaks first.** Google's 100-user Testing cap and weekly disconnects. The worker already crawls faster than the site asks. Free-tier Gemini would break the privacy promise. Gemini 2.5 may not work on a new project.
- **The change.** One shared speed limit of one request every 5 seconds, plus an honest browser name and a daily robots.txt check. Build the newest-list reader (section 10.6) and run it next to today's one for a week. Submit the Google verification. Turn on Gemini billing, turn thinking down and test 3.5 Flash-Lite. Email onlinejobs.ph.
- **Plan B, if the newest list misses too much.** Clean up words (lowercase, trim, merge "va" and "virtual assistant") and search each word on a schedule set by how many people watch it. Words with 5 or more watchers every 10 minutes, 2 to 4 every 20, and 1 every 30 to 60, all inside the 120-per-10-minutes budget.
- **Monthly cost.** USD 28 to 62, PHP 1,750 to 3,875. That is Fly USD 4.30 plus Gemini USD 24 to 58 for about 9,000 letters.
- **Effort.** About 1 to 2 weeks, plus Google's review and a week of side-by-side testing.

### 10.4 Stage B, about 1,000 users

- **What breaks first.** Letter writing in one line. Today searching, writing and sending all happen one after another in one loop ([`applyfirst/saas/worker.py:288-298`](../applyfirst/saas/worker.py#L288-L298)). Up to 10,000 Gemini calls a day at a guessed 5 to 10 seconds each (**UNVERIFIED**) is 14 to 28 hours of work a day in one line, which cannot fit. The expected Gemini bill of USD 243 to 585 a month also reaches or passes the USD 250 cap of Tier 1, and hitting it pauses every letter until the 1st of the next month.
- **The change.** Split the worker in two. Exactly one **poller** owns the speed limit and writes new jobs and alerts to a queue table. Several **senders** take alerts from the queue and write and send 5 to 10 at a time. Give each person their own send queue. Move to Postgres (Supabase Pro or Fly Managed Postgres in Singapore) so web, poller and senders can live on separate machines. Reach Gemini Tier 2 early. Add a free dead-man's-switch check and track letters sent, AI cost per day and round length ([Fly metrics](https://docs.fly.io/monitoring/metrics/)).
- **Monthly cost.** USD 284 to 639, PHP 17,750 to 39,940. Fly about USD 15.50, Postgres USD 25 to 38 ([Supabase pricing](https://supabase.com/pricing), [Fly Managed Postgres](https://docs.fly.io/mpg/)), Gemini USD 243 to 585.
- **Effort.** About 3 to 4 weeks. The Postgres move is the biggest piece.

### 10.5 Stage C, about 10,000 users

- **What breaks first.** Gemini cost and limits, about 900,000 letters a month, which needs Tier 3. And the product itself. 10,000 people applying from one site to a small stream of new jobs (about 2 a minute in one snapshot, **UNVERIFIED**) means many Agad letters per job. The "be first" edge shrinks, and onlinejobs.ph is far more likely to notice.
- **The change.** Tier 3 Gemini, a cheaper model for most letters after a quality test, and your own spend cap. Several senders taking work safely from the Postgres queue so no letter is sent twice. A "leader lock" so only one poller ever runs. Two or more web machines. A formal agreement or feed from onlinejobs.ph, because at this size running without one is a business risk no engineering can remove.
- **Monthly cost.** USD 2,510 to 5,975, PHP 156,900 to 373,400, almost all of it Gemini. Moving most letters to 3.1 Flash-Lite with thinking off would cut Gemini to about USD 1,710.
- **Effort.** About 3 to 5 weeks, plus the model test and partnership talks.

| Stage | Revenue at PHP 199 | Monthly cost | Share that is Gemini |
|---|---|---|---|
| About 100 users | PHP 19,900 (USD 318) | USD 28 to 62, PHP 1,750 to 3,875 | about 86 to 94 percent |
| About 1,000 users | PHP 199,000 (USD 3,184) | USD 284 to 639, PHP 17,750 to 39,940 | about 86 to 92 percent |
| About 10,000 users | PHP 1,990,000 (USD 31,840) | USD 2,510 to 5,975, PHP 156,900 to 373,400 | about 97 to 98 percent |

Revenue is before payment fees and tax. The figures come from the scaling research, built on [Fly pricing](https://docs.fly.io/about/pricing/) and [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing).

### 10.6 The newest-jobs-list idea, and its caveat

**The idea.** The site's search page with no word lists jobs newest first, 30 to a page. In one look on 27 September 2026 the newest 30 covered about 14 minutes, roughly 2 new jobs a minute ([search page](https://www.onlinejobs.ph/jobseekers/jobsearch)). If that holds, a round every 5 minutes needs about 1 list page plus about 10 new job pages. That is about 3,200 requests a day, 19 percent of the ceiling, **and it stays the same whether Agad has 100 or 10,000 users**. Watch words are then matched on our side against each job's title and full text.

**The caveat.** The rate is one Sunday-morning snapshot, so it is **UNVERIFIED** as typical. The page showed "30 out of 287 jobs", so it may apply a default filter and miss some job types, also **UNVERIFIED**. And onlinejobs.ph's own search may match on things we never see. Run both methods side by side for a week and compare what each finds before switching. The newest list still reads their site automatically, so it does not remove the need for permission.

### 10.7 The target shape

```mermaid
flowchart LR
  OJ["onlinejobs.ph<br/>newest-jobs list and job pages"]
  Browser["Browsers"] --> LB["Fly Proxy"]
  subgraph Fly["Fly.io, Singapore"]
    LB --> Web["Web machines<br/>two or more"]
    P["Poller, exactly one<br/>leader lock<br/>1 request per 5 s"]
    S["Senders<br/>as many as needed"]
  end
  PG[("Postgres<br/>jobs, alerts queue,<br/>users, passes")]
  Web <--> PG
  P -->|"a few requests per round"| OJ
  P -->|"new jobs and alerts"| PG
  PG -->|"one alert at a time,<br/>never twice"| S
  S -->|"write the letter"| Gem["Gemini, paid tier<br/>spend cap"]
  S -->|"send it"| GM["Gmail API"]
```

**How to read it.** Web machines and senders can multiply as users grow. The poller cannot. It is exactly one, it owns the site's speed limit, and its traffic depends on how many jobs are posted, not on how many people use Agad.

---

## 11. Getting paid

**In short.** Use PayMongo and sell a 30-day pass for PHP 199 on PayMongo's own payment page, because nobody lets a small business charge GCash automatically every month today. In this app that means three new addresses, two new tables, a few new columns, one deliberate change to the CSP and one new filter in the worker.

### 11.1 The recommendation

- **PayMongo, 30-day passes, Hosted Checkout.** The buyer taps Pay, lands on PayMongo's page, pays with GCash, Maya, QR Ph (the national QR code payment), GrabPay, ShopeePay or card, and PayMongo tells our server by a signed message ([Hosted Checkout](https://docs.paymongo.com/docs/payment-channels-hosted-checkout), [webhook setup](https://docs.paymongo.com/docs/developer-tools-webhook-setup-management)).
- **Why a pass and not a subscription.** PayMongo's automatic renewals cover only cards and Maya, switched on by asking support ([PayMongo Subscriptions](https://docs.paymongo.com/docs/payment-acceptance-subscriptions)). Xendit's GCash auto-debit needs "additional activation process with partner" ([Xendit GCash](https://docs.xendit.co/docs/gcash)), and HitPay says GCash and Maya are "not available for automated recurring billing" ([HitPay](https://hitpayapp.com/blog/recurring-billing-philippines)). For a GCash-first audience, a pass the person renews is the honest default.
- **It already matches the page wording.** The trial note says "No card needed" and that nothing is charged automatically when the trial ends ([`applyfirst/saas/templates/_ui.html:17`](../applyfirst/saas/templates/_ui.html#L17)).
- **Runner-up, Xendit.** It has the best ready-made subscription engine, with a start date you can set to the trial's last day ([Xendit subscriptions](https://docs.xendit.co/docs/subscriptions-overview), [create plan](https://docs.xendit.co/apidocs/create-recurring-plan)). But it does not accept individuals in the Philippines ([Xendit documents](https://docs.xendit.co/docs/philippines-business-documents)), its webhook proof is a fixed shared token rather than a signature ([Xendit webhooks](https://docs.xendit.co/docs/handling-webhooks)), and its fees are **UNVERIFIED**.

### 11.2 Why not Stripe, Paddle or Lemon Squeezy

- **Stripe** does not open accounts for Philippine businesses ([Stripe global](https://stripe.com/global)) and has no GCash or Maya ([Stripe payment methods](https://docs.stripe.com/payments/payment-methods/payment-method-support)). The US-company route through Stripe Atlas costs USD 500 once and USD 100 a year ([Stripe Atlas](https://stripe.com/atlas)), brings a yearly US filing with a USD 25,000 penalty for missing it ([IRS Form 5472](https://www.irs.gov/instructions/i5472)), and a Filipino card would cost about PHP 30.86 on PHP 199 ([Stripe pricing](https://stripe.com/pricing)).
- **Paddle** charges 5% plus 50 US cents, about 21% of a PHP 199 sale, sends products under USD 10 to its sales team, does not support the peso and has no GCash ([Paddle pricing](https://www.paddle.com/pricing), [Paddle currencies](https://developer.paddle.com/concepts/sell/supported-currencies/)).
- **Lemon Squeezy** also charges 5% plus 50 US cents ([Lemon Squeezy pricing](https://www.lemonsqueezy.com/pricing)), and since January 2026 it runs a waitlist while moving users to Stripe Managed Payments ([Lemon Squeezy update](https://www.lemonsqueezy.com/blog/2026-update)), which does not accept Philippine businesses ([Managed Payments eligibility](https://docs.stripe.com/payments/managed-payments/eligibility)).

All three are built for selling software to foreigners in dollars, which is the wrong fit for PHP 199 GCash buyers.

### 11.3 Fees on one PHP 199 payment

PayMongo's prices are "exclusive of VAT", so the figures add 12% VAT, the Philippine sales tax, on the fee. The 12% rate itself is **UNVERIFIED** in this research. Source is [PayMongo pricing](https://www.paymongo.com/pricing).

| Method | PayMongo rate | Fee on PHP 199 | You keep |
|---|---|---|---|
| QR Ph | 1.34% | PHP 2.99 | PHP 196.01 |
| Maya | 1.79% | PHP 3.99 | PHP 195.01 |
| GCash | 2.23% | PHP 4.97 | PHP 194.03 |
| Local card | 3.125% + PHP 13.39 | PHP 21.96 | PHP 177.04 |

Other PayMongo charges. Setup is free, a one-time identity check is PHP 30, the wallet upkeep is PHP 3 to 15 a month and each transfer to your bank is PHP 10 (same page). Money clears in 1 banking day for QR Ph, 2 for e-wallets and 3 for cards ([PayMongo payouts](https://docs.paymongo.com/docs/money-movement-payouts)).

### 11.4 The registration you need

- **An Individual PayMongo account** can take QR Ph, Maya, GrabPay and ShopeePay. **GCash and cards need a registered business** ([account capabilities](https://docs.paymongo.com/docs/account-settings-account-capabilities)).
- **A sole proprietor uploads** a DTI business name certificate, a government ID and BIR Form 2303. DTI is the Department of Trade and Industry, where business names are registered. BIR is the Bureau of Internal Revenue, the tax office, and Form 2303 is its certificate of registration ([Philippine entities](https://docs.paymongo.com/docs/account-settings-philippine-entities)).
- **Approval** takes 3 to 7 business days per e-wallet and 5 to 10 for cards (account capabilities page).
- **The bank account name must match** your registered business or personal name (payouts page).

Section 12.4 covers DTI and BIR.

### 11.5 How it plugs into this app

1. The person taps "Pay PHP 199".
2. Our server creates a PayMongo checkout session with our secret key, and gets back a `checkout_url` on `checkout.paymongo.com` ([quick start](https://docs.paymongo.com/docs/payment-channels-hosted-checkout-quick-start)).
3. The browser is sent there. The person pays.
4. PayMongo sends the browser back to our success page. **That is not proof of payment.**
5. PayMongo posts `checkout_session.payment.paid` to our webhook address. **That is the proof.**
6. We check its signature, record the event once and add 30 days of access.
7. The worker only searches words of people whose access is still valid.

The three new addresses.

| Address | What it does |
|---|---|
| `POST /billing/checkout` | Protected by CSRF like every other form. Makes a `payments` row, creates the checkout session for one "Agad 30-day pass" at 19900 centavos, with our payment id as `reference_number` and emailed receipts on, then redirects to `checkout_url` |
| `GET /billing/return` | Shows "Salamat, confirming your payment" and reads our own database. It never grants access |
| `POST /webhooks/paymongo` | No session and no CSRF. Checks the signature on the raw bytes first, records the event id, then extends access once per payment |

**The CSP note, important.** Our CSP says `form-action 'self'` ([`applyfirst/saas/app.py:229-232`](../applyfirst/saas/app.py#L229-L232)). Chrome blocks a form post that then redirects to another site not listed there, while Firefox does not ([MDN form-action](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/form-action)). Most of your users are on Android Chrome, so a Pay form would fail silently for them. The Google button already dodges the same rule by being a plain link. Here the better fix is to keep the form, with its CSRF token, and add PayMongo to the rule, as `form-action 'self' https://checkout.paymongo.com`. The tests pin the exact CSP text in `tests/_saas_client.py`, so this is a deliberate, tested change to a frozen rule. No script change is needed, because the payment page runs on PayMongo's site.

**Billing emails** should come from the server's own mail account, the one the reconnect email uses ([`applyfirst/saas/reconnect.py:223-249`](../applyfirst/saas/reconnect.py#L223-L249)), never through the person's Gmail permission. Google's policy limits that permission to what you disclosed it is for ([API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)).

### 11.6 What to store

- **On `users`**, add `trial_ends_at` and `paid_until`. Later, for auto-renew, `paymongo_customer_id` and `paymongo_subscription_id`. The unused `plan` column is there today, always "free" ([`applyfirst/saas/db.py:234`](../applyfirst/saas/db.py#L234)).
- **A new `payments` table** with our own id (sent as `reference_number`), `user_id`, `checkout_session_id`, `payment_id`, `amount_centavos`, `method`, `status` (pending, paid, refunded, disputed), `days_granted`, `period_start`, `period_end`, `created_at` and `paid_at`.
- **A new `webhook_events` table** keyed by PayMongo's event id, with `type`, `received_at` and `processed_at`. Skip any event id already seen ([best practices](https://docs.paymongo.com/docs/developer-tools-best-practices)).
- **The access rule** is "now is before the later of `trial_ends_at` and `paid_until`, plus 2 days of grace". Apply it where the worker lists the words to search ([`applyfirst/saas/db.py:598-609`](../applyfirst/saas/db.py#L598-L609)) and where it picks watchers for a job ([`applyfirst/saas/db.py:636-665`](../applyfirst/saas/db.py#L636-L665)). That also saves Gemini and Gmail calls for people who stopped paying.

The schema, meaning the table layout, is at step 5 today ([`applyfirst/saas/db.py:33`](../applyfirst/saas/db.py#L33)), so this becomes step 6, and the tests must use the version constant rather than a number.

### 11.7 The trial rule

- Start the 14-day trial with **no payment details**, at the moment the person first presses Start. `activated_at` is already stamped once and kept forever ([`applyfirst/saas/db.py:393-398`](../applyfirst/saas/db.py#L393-L398)).
- Store `trial_ends_at` once and never reset it. Tie it to the Google id, which is already unique ([`applyfirst/saas/db.py:149`](../applyfirst/saas/db.py#L149)), so signing up again never gives a second trial.
- At the end the person buys a 30-day pass. This avoids two PayMongo gaps, no trial setting and a first subscription payment due within 24 hours ([PayMongo Subscriptions](https://docs.paymongo.com/docs/payment-acceptance-subscriptions)).
- Show a banner from 3 days before the end, keep 2 days of grace, then pause the worker for that person and keep all their data, so paying resumes at once. Offer 90-day passes later to cut fees and reminders.
- No Philippine rule specific to free trials was found, **UNVERIFIED**. Good practice anyway is to show the price and end date before the trial starts.

### 11.8 Webhooks

- The header is `Paymongo-Signature`, with parts `t` (a timestamp), `te` (test signature) and `li` (live signature) ([webhook setup](https://docs.paymongo.com/docs/developer-tools-webhook-setup-management)).
- The signature is HMAC-SHA256 of `t`, a dot and the raw body, using the endpoint's secret. HMAC is a seal made with a secret, so only someone who holds the secret can make a matching one. Compare in constant time and check it before reading the body ([best practices](https://docs.paymongo.com/docs/developer-tools-best-practices-1)).
- Answer within 30 seconds. Failed deliveries are retried up to 12 times ([webhook concepts](https://docs.paymongo.com/docs/developer-tools-webhooks-key-concepts)).
- Events to handle. `checkout_session.payment.paid` adds 30 days. `refund.succeeded` and `dispute.created` mark the payment and pull back that payment's days ([webhook events](https://docs.paymongo.com/docs/developer-tools-webhooks-events)).

In code this is about ten lines with Python's own `hmac` module. Rebuild the signature from the raw bytes with our secret, compare the two in a way that takes the same time whether they match or not, so an attacker learns nothing from the timing, and refuse anything older than 5 minutes. That age limit is our own choice, not PayMongo's. Confirm the timestamp format against a real test webhook, because that detail is **UNVERIFIED**.

### 11.9 The payment, in a picture

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as Agad web app
    participant P as PayMongo
    participant D as Database
    participant W as Worker
    B->>A: POST /billing/checkout with CSRF token
    A->>D: insert payments row, pending
    A->>P: create checkout session, 19900 centavos, reference number
    P-->>A: checkout_url
    A-->>B: 303 to checkout.paymongo.com
    B->>P: pay with GCash, Maya, QR Ph or card
    P-->>B: redirect to /billing/return
    B->>A: GET /billing/return
    A-->>B: Salamat, confirming your payment
    P->>A: POST /webhooks/paymongo, checkout_session.payment.paid
    Note over A: check the signature on the raw bytes first
    alt event id already seen
        A-->>P: 200, nothing to do
    else new event
        A->>D: record event id
        A->>D: mark payment paid, paid_until moves 30 days later
        A-->>P: 200
    end
    W->>D: list watch words of people with valid access only
```

### 11.10 Later, auto-renew for Maya and cards

Once PayMongo support switches Subscriptions on, offer auto-renew to people who pick Maya or a card. Failed renewals are retried "once per day, up to 3 times", then the subscription becomes `unpaid` ([PayMongo Subscriptions](https://docs.paymongo.com/docs/payment-acceptance-subscriptions)). Listen for `subscription.invoice.paid`, `subscription.past_due` and `subscription.unpaid`.

Ask PayMongo support four things first. Can GCash subscriptions be switched on? Can Maya and card subscriptions be switched on for your account type? Is card vaulting available? Which card-security questionnaire applies? All four answers are **UNVERIFIED** today.

For the first handful of beta users, a PayMongo payment link made in the dashboard needs no code at all, and you match payments to people by hand (Hosted Checkout page). That is fine for 10 people, not for 100.

---

## 12. The MVP and the launch checklist

**In short.** A paid Agad needs about 15 to 20 working days of building plus 2 to 4 weeks of waiting on Google, the government and PayMongo, which can overlap, so a paid launch is about 4 to 6 weeks away. Those figures are estimates, and this section is research, not legal or tax advice.

MVP means minimum viable product, the smallest version people would pay for. Agad's MVP is done when a stranger on an Android phone can find Agad, sign up, get useful applications in Gmail, pay after the trial, cancel or delete themselves, and you can run it alone without being woken at 3 in the morning.

### 12.1 Must have before the first peso, in the order to do it

Sign-in, onboarding, watching and sending are already built. Start the slow, waiting-heavy items first so the waiting overlaps the building. Effort is for one developer who knows this code. S is about half a day, M is 1 to 2 days, L is 3 to 7 days.

| When | # | Item | Today | Effort |
|---|---|---|---|---|
| Week 1 | 1 | Rotate the Google client secret shown in a screenshot | Not done | S |
| Week 1 | 2 | Own domain, HTTPS, verified in Google Search Console | Not done | S |
| Week 1 | 3 | Business paperwork. DTI name (national scope), barangay clearance and Mayor's permit, BIR on ORUS with the 8% option, Form 2303 and the Seal Badge | Not started | S of your time, 1 to 3 weeks of waiting (**UNVERIFIED**, depends on your city) |
| Week 1 | 4 | onlinejobs.ph politeness. Permission email, 5-second limit, honest browser name, a cadence the pages can keep | Not done | S, then wait for a reply |
| Week 1 | 5 | Gemini billing on, thinking turned down, a spend cap | Billing off, no caps | S to M |
| Week 1 | 6 | UptimeRobot on `/health`, the alert webhook, then `notify --test` | Code ready, not set up | S |
| Week 2 | 7 | Legal pages and homepage footer updated (section 12.4) | Partly | M |
| Week 2 | 8 | Self-serve account deletion, which revokes the Google pass and deletes the rows | Promised, no code | M |
| Week 2 | 9 | Rate limits beyond `/auth/`, fix "start without Gmail and be skipped forever", pin library versions | Open | M |
| Week 2 | 10 | Delete old `jobs` and `user_job_alerts` rows, copy backups off the machine, practise one restore and write it down | Never done | M |
| Week 2 | 11 | A real sign-up gate, or none, since `INVITE_ONLY` is only wording | Not a gate | S |
| Week 2 | 12 | NPC (National Privacy Commission) sworn declaration, NPC breach system, a one-page security policy and breach steps | Not started | S, plus a notary |
| Week 2 | 13 | `support@` and `privacy@` addresses on your domain, answered within 7 days | Personal Gmail only | S |
| Week 2 | 14 | Demo video, publish "In production", "Prepare for verification", submit ([how](https://support.google.com/cloud/answer/13461325)) | Testing mode | S, then 1 to 3 weeks of waiting |
| Weeks 3 and 4 | 15 | Open the PayMongo account with the DTI certificate and Form 2303 | Not started | S, plus the approval wait |
| Weeks 3 and 4 | 16 | Billing with the 14-day trial, cancel, pause and an invoice email per charge (section 11) | Not built | L |
| Weeks 3 and 4 | 17 | Test the whole paid path in PayMongo's test mode, then one real payment of your own ([testing](https://docs.paymongo.com/docs/payment-acceptance-testing)) | Not started | S |

### 12.2 Can wait until after launch

- Moving off SQLite or adding a second machine. The crawl pace, not the database, is the limit.
- A self-serve data export button. Handle requests by email at first.
- NPC registration and its seal, unless you cross a trigger in section 12.4.
- VAT registration, needed only above PHP 3,000,000 a year ([BIR EOPT flyer](https://bir-cdn.bir.gov.ph/BIR/pdf/flyer-eopt.pdf)).
- A phone app, more job sites, analytics, referral codes and annual plans.
- CASA. Never needed unless you add a restricted Gmail scope.

### 12.3 The launch-day gate

All of these must be true.

1. Google shows the app as verified for `gmail.send`, with no unverified screen.
2. A stranger's account can sign up, trial, pay, cancel and delete itself.
3. A restore from an off-machine backup has worked at least once.
4. The uptime monitor has paged you at least once in a test.
5. Every promise on `/privacy`, `/terms` and the homepage is true in the code.

### 12.4 The legal basics

**Data Privacy Act (RA 10173) and the NPC, the National Privacy Commission.**

- Agad decides what personal data to collect and why, so you are a "personal information controller". The Act applies at any size, and you stay responsible for data you hand to Google, Fly.io and Gemini, including abroad ([Data Privacy Act](https://privacy.gov.ph/data-privacy-act/), Sec. 21).
- **Registration.** NPC Circular 2022-04 requires registering your systems if you have 250 or more staff, or process sensitive personal information of 1,000 or more people, or pose a likely risk ([Circular 2022-04](https://privacy.gov.ph/wp-content/uploads/2023/05/Circular-2022-04-1.pdf), Sec. 5). Otherwise you file a notarized sworn declaration instead, called Annex 1, through the NPC's online system ([Annex 1](https://privacy.gov.ph/wp-content/uploads/2023/05/Circular-2022-04-Annex-1-1.pdf), [NPC FAQs](https://privacy.gov.ph/pips-and-pics/faqs/)). Whether Annex 1 is free is **UNVERIFIED**.
- **The 1,000-person trigger.** Philippine law counts education, age and marital status as sensitive (Data Privacy Act, Sec. 3(l)). People paste their schooling and experience into their standard message, and the form asks for real experience ([`applyfirst/saas/templates/onboarding_profile.html:62`](../applyfirst/saas/templates/onboarding_profile.html#L62)). Past 1,000 users you will likely need to register, which is an estimate, not an NPC ruling. Or tell people in the form not to include age, marital status or ID numbers.
- **Data Protection Officer.** For a solo business that is you, with a separate address such as `privacy@yourdomain` (Circular 2022-04, Sec. 8).
- **Breaches.** Tell the NPC and affected people within 72 hours of knowing ([NPC Circular 16-03](https://privacy.gov.ph/wp-content/uploads/2022/01/sgd-npc-circular-16-03-personal-data-breach-management.pdf)). Register in the NPC breach system even when exempt from registration (NPC FAQs).
- **The privacy page is missing** people's rights and their right to complain to the NPC, your business name and address, the hosting provider and country (Fly.io, Singapore), and how long backups keep data (Data Privacy Act, Sec. 16). The 30-working-day answer time for rights requests is **UNVERIFIED** on the NPC's own page.

**DTI and BIR.**

- **DTI business name.** PHP 200 barangay, 500 city, 1,000 regional or 2,000 national scope, plus PHP 30 stamp tax, valid 5 years ([DTI BNRS FAQ](https://bnrs.dti.gov.ph/faq)).
- **BIR registration** on ORUS with Form 1901 gives Form 2303, for PHP 30 stamp tax. The PHP 500 yearly fee was abolished from 22 January 2024 ([BIR EOPT flyer](https://bir-cdn.bir.gov.ph/BIR/pdf/flyer-eopt.pdf)).
- **The 8% option.** A sole proprietor under PHP 3,000,000 a year can pay 8% on sales above PHP 250,000, instead of both the graduated income tax and the 3% percentage tax ([Grant Thornton](https://www.grantthornton.com.ph/insights/articles-and-updates1/lets-talk-tax/the-8-tax-for-self-employed-individuals/)). When exactly to elect it is **UNVERIFIED**, ask your Revenue District Office.
- **Invoices.** Since 27 April 2024 the invoice is the proof of a sale of services ([BIR RMC 77-2024](https://bir-cdn.bir.gov.ph/BIR/pdf/RMC%20No.%2077-2024%20Digest.pdf)). Whether you may email a PDF invoice without a BIR-registered system is **UNVERIFIED**, ask an accountant.
- **Registration Seal Badge.** Online businesses must show a free BIR badge on their website ([BIR RMC 38-2026](https://bir-cdn.bir.gov.ph/BIR/pdf/RMC%20No.%2038-2026%20Digest.pdf)). The no-penalty deadline of 31 October 2026 comes from a news report of RMC 99-2026 ([Manila Times](https://www.manilatimes.net/2026/09/26/business/top-business/bir-sets-oct-deadline-for-registration-badges/2433272)), not from the circular itself.
- **Gateway withholding.** Payment providers withhold 1% on half of what they pay you once yearly payouts pass PHP 500,000, about 210 paying users. It is a credit against your income tax ([BIR RR 16-2023](https://bir-cdn.bir.gov.ph/BIR/pdf/RR%2016-2023.pdf)).

**Internet Transactions Act (RA 11967).** Selling a service to online consumers through your own site makes Agad an "e-retailer". The homepage must show your business name, a physical address, a phone number and an email, you must issue invoices for all sales, and you need a complaints process where a complaint counts as unresolved after 7 calendar days ([RA 11967](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/96902), Secs. 4, 23 and 24). The homepage has none of the business details today.

**Google's own rules.** Keep a Limited Use statement on the privacy page, which `/privacy` already has ([`applyfirst/saas/templates/privacy.html:70`](../applyfirst/saas/templates/privacy.html#L70)), honour deletion requests, and never use Google user data to train AI beyond that person's own use ([Workspace API User Data Policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)).

---

## 13. Glossary

**In short.** Every technical word this guide uses, in one plain line each, in alphabetical order.

| Word | What it means |
|---|---|
| AAD | Extra data stamped into a lock's seal. Here the user id, so a locked pass only opens on its own row |
| Access token | A short-lived pass from Google, used for one send and never saved |
| AES-256-GCM | A standard lock for data that also notices if any byte was changed |
| Alert | One row that means "send this job to this person" |
| API | A door one program offers so other programs can use it |
| Baseline | A quiet first search that stores what is already posted and tells nobody |
| Basecoat | A small ready-made style kit with the shadcn/ui look, trimmed for the sign-up pages |
| BIR | The Bureau of Internal Revenue, the Philippine tax office |
| Blind | When onlinejobs.ph returns nothing, even for the canary search |
| Cache | A saved copy of work already done, here finished letters |
| Caddy | A front-door web server that handles the padlock certificate by itself |
| Canary | A test you trust to always work, so its failure points at the other side |
| CASA | Google's paid yearly security audit, needed only for restricted Gmail scopes |
| Cloudflare | A service many sites sit behind that can spot and block robots |
| Cookie | A small note a site asks the browser to keep and send back each visit |
| Crawl-delay | A robots.txt line asking robots to wait that many seconds between requests |
| CSP | Content Security Policy, a rule list telling the browser where a page may load things from |
| CSRF | A trick where another site makes your browser press a button on ours. Stopped by a secret token |
| CSS | The language of style rules, the colours, sizes and spacing of a page |
| Data key (DEK) | The fresh key made for each Gmail pass, itself locked by the master key |
| Dead-man's switch | An alarm that fires when an expected signal stops |
| Docker image | A sealed box holding Python, the libraries and our code |
| DPO | Data Protection Officer, the person answerable for privacy |
| DTI | The Department of Trade and Industry, where business names are registered |
| Environment variable | A named setting handed to a program when it starts |
| Exit code | A number a program leaves behind to say why it stopped |
| Fan-out | Turning one job into one alert for each person who should get it |
| FastAPI | The Python toolkit the web app is built with |
| Fly.io | The hosting service chosen for the beta |
| Form 2303 | The BIR's certificate of registration, which payment companies ask for |
| Gemini | Google's AI, which tailors each letter |
| `gmail.send` | The Google permission to send email as a person, and nothing else |
| Hash, fingerprint | A short code made from some text that changes completely if any letter changes |
| HMAC | A seal made with a secret, so only someone with the secret can make a matching one |
| Hosted Checkout | PayMongo's own payment page, which our app sends the buyer to |
| HTTPS | The padlocked way browsers talk to sites |
| ID card (ID token) | Google's signed note saying who the person is, checked at sign-in |
| Jinja | The template engine that fills in the pages on the server |
| JSON | A plain text format for data that both people and programs can read |
| Leader lock | A rule that lets only one copy of a program do a job at a time |
| Linter, type checker | Tools that scan code for mistakes without running it. This project has neither |
| Log event | One line a program writes about what just happened |
| Master key | The one key that locks every data key. It never enters the database |
| Middleware | Code that every request and reply passes through |
| Migration | One numbered step that builds or changes the database layout |
| MVP | Minimum viable product, the smallest version people would pay for |
| Nonce | A one-time value Google must copy into its ID card, proving the card is fresh |
| NPC | The National Privacy Commission of the Philippines |
| OAuth | Google's way for a person to let an app do something without sharing their password |
| ORUS | The BIR's online registration system |
| PayMongo | A Philippine payment company, the recommended way to take money |
| PKCE | A secret whose fingerprint goes to Google first and the secret itself later, proving the same app finished the sign-in |
| Poller, sender | In the scaling plan, the one program that reads the site, and the programs that write and send letters |
| Port | A numbered door on a machine that one program listens at |
| Postgres | A database server that several machines can share |
| Proxy | A front-door server that takes each visitor's request and passes it to the app |
| QR Ph | The national QR payment standard, the cheapest PayMongo method |
| Quota unit | Google's way of counting API use. One Gmail send is 100 units |
| Rate limit | A cap on how many requests one address may make in a time window |
| Redirect | The server telling the browser to go to another address at once |
| Refresh token | A long-lived pass from Google that lets the worker send later |
| robots.txt | A file where a site tells robots its rules |
| Round | One full pass of the worker, also called a cycle |
| Route | An address the web app answers, with a function behind it |
| Schema | The layout of the database tables |
| Scope | One permission asked of Google. Sensitive and restricted scopes need review |
| Search Console | Google's tool where you prove you own a domain |
| Shell | A command line typed straight into a machine |
| Smoke script | A quick end-to-end check that draws every page and submits every form |
| SMTP | The ordinary way one mail server hands email to another |
| SQL | The database's own command language |
| SQLite | A database that is just one file on disk |
| State | A one-time ticket that proves Google's answer belongs to this browser |
| System user | An account with no login that a program runs as |
| systemd | Linux's built-in manager that starts and restarts programs |
| Tailscale | A private network between your own devices |
| Temperature | An AI setting for how adventurous the wording is |
| Template | An HTML page with blanks the server fills in |
| Tenant | One customer's private slice of a shared system |
| Testing mode | Google's beta setting, 100 test users and 7-day Gmail connections |
| Thinking tokens | The AI's hidden reasoning, billed like normal output |
| Token | For AI pricing, a piece of text about three quarters of a word |
| Unit file | systemd's instruction card for one program |
| UTC | World time. The Philippines is 8 hours ahead |
| uvicorn | The program that listens for browsers and hands requests to FastAPI |
| V1, V2 | Your personal tool, and the public service |
| VAT | Value-added tax, 12% in the Philippines |
| Vendored | A copy of someone else's code kept inside our project |
| Volume | A Fly disk that survives restarts and plugs into one machine |
| WAL | A SQLite mode that lets one program read while another writes |
| Watch word | A search term a person added. The code calls it a keyword |
| Watchdog | A timer that ends a program that stopped making progress |
| Webhook | A secret web address one service posts messages to |
| Worker | The background program that searches, writes and sends |
| 200, 302, 400, 403, 404, 429, 503 | Web answer codes. OK, go elsewhere, bad request, forbidden, not found, slow down, not healthy |

---

## 14. Sources

**In short.** Every outside fact above links to one of these pages, grouped by topic. They were read and fact-checked on 27 September 2026.

**onlinejobs.ph and crawling**

[onlinejobs.ph terms of use](https://www.onlinejobs.ph/terms) · [onlinejobs.ph robots.txt](https://www.onlinejobs.ph/robots.txt) · [onlinejobs.ph llms.txt](https://www.onlinejobs.ph/llms.txt) · [onlinejobs.ph job search page](https://www.onlinejobs.ph/jobseekers/jobsearch) · [RFC 9309, the robots standard](https://www.rfc-editor.org/rfc/rfc9309.html) · [Cloudflare bot score](https://developers.cloudflare.com/bots/concepts/bot-score/)

**Google sign-in, Gmail and verification**

[Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) · [Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification) · [Restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) · [Brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification) · [Verification requirements](https://support.google.com/cloud/answer/13464321) · [Demo video requirements](https://support.google.com/cloud/answer/13804565) · [Testing and production, 100 users, 7-day expiry](https://support.google.com/cloud/answer/15549945) · [Unverified apps and the 100 new-user cap](https://support.google.com/cloud/answer/7454865) · [Submitting for verification](https://support.google.com/cloud/answer/13461325) · [OAuth 2.0 overview](https://developers.google.com/identity/protocols/oauth2) · [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy) · [Google Workspace API User Data and Developer Policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy) · [Authorized domains](https://support.google.com/googleapi/answer/6158849) · [Gmail API usage limits](https://developers.google.com/workspace/gmail/api/reference/quota) · [Gmail API error handling](https://developers.google.com/workspace/gmail/api/guides/handle-errors) · [Gmail sending limits, personal](https://support.google.com/mail/answer/22839?hl=en) · [Gmail sending limits, Workspace](https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace)

**Gemini**

[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) · [Gemini 2.5 Flash model page](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash) · [Gemini API changelog](https://ai.google.dev/gemini-api/docs/changelog) · [Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations) · [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking) · [Gemini API terms](https://ai.google.dev/gemini-api/terms) · [Gemini rate limits and tiers](https://ai.google.dev/gemini-api/docs/rate-limits) · [Gemini billing and spend caps](https://ai.google.dev/gemini-api/docs/billing) · [Gemini batch mode](https://ai.google.dev/gemini-api/docs/batch-mode)

**Hosting and databases**

[Fly.io pricing](https://docs.fly.io/about/pricing/) · [Fly.io free trial](https://docs.fly.io/about/free-trial/) · [Fly.io volumes](https://docs.fly.io/volumes/overview/) · [Fly.io LiteFS](https://docs.fly.io/litefs/) · [Fly.io Managed Postgres plans](https://docs.fly.io/mpg/) · [Fly.io Managed Postgres overview](https://docs.fly.io/postgres/) · [Fly.io regions](https://docs.fly.io/reference/regions/) · [Fly.io metrics](https://docs.fly.io/monitoring/metrics/) · [SQLite write-ahead logging](https://www.sqlite.org/wal.html) · [SQLite, appropriate uses](https://www.sqlite.org/whentouse.html) · [Supabase pricing](https://supabase.com/pricing) · [Supabase compute sizes](https://supabase.com/docs/guides/platform/compute-and-disk) · [Neon pricing](https://neon.com/pricing) · [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) · [Healthchecks.io pricing](https://healthchecks.io/pricing/) · [BSP reference exchange rate, 4 September 2026](https://www.bsp.gov.ph/Lists/RERB/Attachments/2349/04Sep2026.pdf)

**Payments**

[PayMongo pricing](https://www.paymongo.com/pricing) · [PayMongo Subscriptions product page](https://www.paymongo.com/products/accept-payments/subscriptions) · [PayMongo Subscriptions docs](https://docs.paymongo.com/docs/payment-acceptance-subscriptions) · [PayMongo account capabilities](https://docs.paymongo.com/docs/account-settings-account-capabilities) · [PayMongo Philippine entities](https://docs.paymongo.com/docs/account-settings-philippine-entities) · [PayMongo Hosted Checkout](https://docs.paymongo.com/docs/payment-channels-hosted-checkout) · [PayMongo Hosted Checkout quick start](https://docs.paymongo.com/docs/payment-channels-hosted-checkout-quick-start) · [PayMongo webhook setup](https://docs.paymongo.com/docs/developer-tools-webhook-setup-management) · [PayMongo signature best practices](https://docs.paymongo.com/docs/developer-tools-best-practices-1) · [PayMongo developer best practices](https://docs.paymongo.com/docs/developer-tools-best-practices) · [PayMongo webhook concepts](https://docs.paymongo.com/docs/developer-tools-webhooks-key-concepts) · [PayMongo webhook events](https://docs.paymongo.com/docs/developer-tools-webhooks-events) · [PayMongo payouts](https://docs.paymongo.com/docs/money-movement-payouts) · [PayMongo testing](https://docs.paymongo.com/docs/payment-acceptance-testing) · [Xendit GCash](https://docs.xendit.co/docs/gcash) · [Xendit subscriptions](https://docs.xendit.co/docs/subscriptions-overview) · [Xendit create plan](https://docs.xendit.co/apidocs/create-recurring-plan) · [Xendit Philippine business documents](https://docs.xendit.co/docs/philippines-business-documents) · [Xendit webhooks](https://docs.xendit.co/docs/handling-webhooks) · [HitPay, recurring billing in the Philippines](https://hitpayapp.com/blog/recurring-billing-philippines) · [Stripe global availability](https://stripe.com/global) · [Stripe payment method support](https://docs.stripe.com/payments/payment-methods/payment-method-support) · [Stripe pricing](https://stripe.com/pricing) · [Stripe Atlas](https://stripe.com/atlas) · [IRS Form 5472 instructions](https://www.irs.gov/instructions/i5472) · [Stripe Managed Payments eligibility](https://docs.stripe.com/payments/managed-payments/eligibility) · [Paddle pricing](https://www.paddle.com/pricing) · [Paddle supported currencies](https://developer.paddle.com/concepts/sell/supported-currencies/) · [Lemon Squeezy pricing](https://www.lemonsqueezy.com/pricing) · [Lemon Squeezy 2026 update](https://www.lemonsqueezy.com/blog/2026-update) · [MDN, CSP form-action](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/form-action)

**Philippine law, tax and business**

[Data Privacy Act of 2012, RA 10173](https://privacy.gov.ph/data-privacy-act/) · [NPC Circular 2022-04](https://privacy.gov.ph/wp-content/uploads/2023/05/Circular-2022-04-1.pdf) · [NPC Circular 2022-04 Annex 1](https://privacy.gov.ph/wp-content/uploads/2023/05/Circular-2022-04-Annex-1-1.pdf) · [NPC FAQs](https://privacy.gov.ph/pips-and-pics/faqs/) · [NPC Advisory 2021-01](https://privacy.gov.ph/wp-content/uploads/2021/02/NPC-Advisory-2021-01-FINAL.pdf) · [NPC Circular 16-03, breach management](https://privacy.gov.ph/wp-content/uploads/2022/01/sgd-npc-circular-16-03-personal-data-breach-management.pdf) · [DTI BNRS FAQ](https://bnrs.dti.gov.ph/faq) · [BIR flyer on the Ease of Paying Taxes Act](https://bir-cdn.bir.gov.ph/BIR/pdf/flyer-eopt.pdf) · [BIR RMC 77-2024 digest, invoicing](https://bir-cdn.bir.gov.ph/BIR/pdf/RMC%20No.%2077-2024%20Digest.pdf) · [BIR RMC 38-2026 digest, Registration Seal Badge](https://bir-cdn.bir.gov.ph/BIR/pdf/RMC%20No.%2038-2026%20Digest.pdf) · [Manila Times, BIR sets October deadline for registration badges](https://www.manilatimes.net/2026/09/26/business/top-business/bir-sets-oct-deadline-for-registration-badges/2433272) · [BIR RR 16-2023, withholding by payment providers](https://bir-cdn.bir.gov.ph/BIR/pdf/RR%2016-2023.pdf) · [Grant Thornton, the 8% tax option](https://www.grantthornton.com.ph/insights/articles-and-updates1/lets-talk-tax/the-8-tax-for-self-employed-individuals/) · [Internet Transactions Act, RA 11967](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/96902) · [PayMongo guide to registering an online business](https://www.paymongo.com/blog/how-to-register-online-business-philippines)

**Inside the repo**

- `Handoff.md`, the project diary, for live server facts and history.
- `docs/OPERATIONS.md`, every production command, the cost model and the known gaps.
- `docs/LOCAL-TEST.md`, running V2 on your PC with a real Google account.
- `docs/legal/google-verification.md`, the Google runbook and the ready scope reason.
- `docs/SYSTEM-DESIGN.md`, the original design. Its data drawing is older than the code.
