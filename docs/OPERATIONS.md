# Running Agad in production

What the backend really does, what it costs, what breaks, and exactly what you type when it does.

Written 2026-09-21 from the code itself, with every claim checked against a file and line, and the
money and downtime claims checked a second time by a separate pass. Prices were read from the
vendors' own pages on that date, so re-check them before you rely on them.

**Status when this was written.** V2 has never been deployed anywhere. No Fly app, no Google OAuth
client, no real user. Every number below comes from reading the code and the vendor docs, never
from watching it run in production. Your first deploy is also your first real measurement.

---

## 1. Before you launch

The 2026-09-21 audit found six things missing. The code for the first five is now in place
(2026-09-23). Three of them still need **you** to set something, because the code cannot choose
your credential, your webhook or your uptime monitor for you.

| # | What was wrong | What the code does now | What you still do |
|---|---|---|---|
| 1 | No Gemini credential anywhere in the deploy, so every letter was the user's own unchanged message plus "(AI unavailable — answers are blank; edit before sending.)" | `fly.toml` and `saas-env.sample` list it as required, and an unfilled placeholder such as `<your-gemini-key>` counts as missing. In production a worker with no credential logs `ai_not_configured` at every start, sends you one alert, and `/health` returns **503** with `"ai": "off"` until it is set. A credential that is set but wrong or unbilled is caught too: when every AI call fails for two cycles in a row, the worker logs `ai_all_failed` and alerts you, and each failure logs `ai_call_failed` with its status code | `fly secrets set GEMINI_API_KEY=... -a <app>`, with billing on first (see below) |
| 2 | SaaS logging was never switched on, so every structured event was thrown away | Logging is **on by default** in the web server, the worker and the backup command (`APPLYFIRST_LOG_JSON`, default 1): one JSON object per line on stderr, read with `fly logs` or `journalctl` | Nothing |
| 3 | No alert destination, so the dead-man switch fired into a log nobody read | A production worker with no channel logs `owner_alerts_not_configured` at every start. A webhook answering 4xx no longer counts as delivered, and its URL never reaches a log. `python -m applyfirst.saas.notify --test` sends a test alert and says which channel delivered it. A blind worker also turns `/health` 503, so your uptime monitor pages you even with no webhook. "Blind" now means the site itself did not answer: when every watched term comes back empty, one search for "virtual assistant" decides, so one user watching a term with no posts pages nobody. A worker that cannot load its master key alerts you before it exits | `fly secrets set APPLYFIRST_ALERT_WEBHOOK=<slack-or-discord-url> -a <app>`, then run the test command in section 2 |
| 4 | The Fly worker watchdog was dead code, so a worker that crashed or hung was never restarted, while `/healthz` kept saying "ok" | `entrypoint.sh` runs the worker in a restart loop (10s, doubling to 5 minutes while it keeps failing fast). Inside the worker a watchdog ends any cycle that goes 15 minutes with no sign of progress (`worker_stalled`, exit 70), and the loop starts a fresh one. Every search attempt, every job stored and every alert handled counts as progress, a failed search included, so a slow outage at onlinejobs.ph reads as blind rather than as a hang. On Oracle, systemd's `Restart=always` does the restarting | Point an uptime monitor (UptimeRobot, free) at `https://<app>.fly.dev/health` |
| 5 | Nothing ever ran a backup on Fly | With `APPLYFIRST_BACKUP_IN_WORKER=1` (set in `fly.toml`) the worker takes the day's backup after its first cycle of each UTC day into `/data/backups`, keeping 7. A failure is logged as `backup_failed`, retried after every cycle, and alerted once per 6 hours. A backup that fails or is killed part-way never leaves a truncated file under a real backup name, its temporary files are removed, and it refuses to start when the disk lacks room for twice the database. On Oracle a failed nightly backup now alerts you too | Pull one off the box now and then, and practise the restore in section 5 once |
| 6 | Google forces a 7-day refresh-token expiry while the app is unverified, and the code clears the credential silently | **Still open.** Every beta user stops receiving anything once a week and is told nothing | Send a "reconnect Gmail" email via the existing `notify.py` SMTP path when the credential is cleared |

Two more worth knowing before the first paying user.

**A free Gemini key makes your privacy policy untrue.** Google's terms say it uses unpaid API
content to improve its products and that human reviewers may read it. Your privacy page promises
the opposite. Turn billing on before anyone real signs up.

**Invite-only is wording, not a gate.** `INVITE_ONLY` in `_ui.html:8` only changes the buttons.
There is no allowlist and no server-side check. The real gate is Google's test-user list, capped
at 100 people. The day you publish the app to Production, sign-up is open to the whole internet
with no code change.

---

## 2. Is it alive

```bash
# Fly
fly status -a <app>                       # expect exactly ONE machine, always
fly logs -a <app>
curl -s https://<app>.fly.dev/health      # the only check that can see a dead worker
curl -s https://<app>.fly.dev/healthz     # always "ok", tells you almost nothing
```

```bash
# Oracle
systemctl status applyfirst-saas-web applyfirst-saas-worker
journalctl -u applyfirst-saas-worker -f
curl -s https://<domain>/health
```

**Read `/health` properly.** It returns 503 in four cases. The worker heartbeat is older than
2.5 times the poll interval, which is 25 minutes at the 600 second default (`"worker": "stale"`).
The worker has never finished a cycle that long after the web server started
(`"worker": "never_ran"`). onlinejobs.ph has not answered for 3 cycles in a row
(`"polling": "blind"`). Or this is production and the worker is running with no Gemini
credential (`"ai": "off"`), unless you set `APPLYFIRST_AI_OFF_OK=1` to say the AI is off on
purpose. The AI state is the one the worker recorded when it last started, so after changing the
credential, restart the worker. It reports `"db": "ok"` as a hardcoded string, so it tells you
nothing about the database. If the database file is actually
corrupt, `/health` returns **500**, not 503, and so does every page on the site, while `/healthz`
keeps saying "ok".

**Put an uptime monitor on `/health`.** It is the only thing that pages you when the worker has
stopped or gone blind with no webhook set. Do not point Fly's own check at it: with one machine, a
failing Fly check takes the whole site off the air.

**Check the alert channel reaches you**, once after setting it and again after any change.

```bash
fly ssh console -a <app> -C "python -m applyfirst.saas.notify --test"
# Oracle
sudo -u applyfirst sh -c 'cd /opt/applyfirst && exec .venv/bin/python -m applyfirst.saas.notify --test'
```

It prints `configured: webhook, delivered by: webhook` and exits 0 when it worked. If the webhook
failed and SMTP stepped in, it says so and exits 1, because the channel you meant is broken.

**The log events worth a search**, all at CRITICAL or ERROR. `worker_stalled` (the watchdog ended a
hung cycle), `worker_blind`, `ai_not_configured`, `ai_all_failed`, `owner_alerts_not_configured`,
`backup_failed`, `worker_cycle_crashed`, `worker_no_master_key`. At WARNING, `ai_call_failed`
carries the status code of each failed AI call, and `search_failed` each failed search. On Fly, `[entrypoint] worker exited with status`
lines show each restart.

---

## 3. Stop the bleeding

Four switches that already exist. Know them before you need them.

| Goal | Do this | What actually happens |
|---|---|---|
| Stop all AI spend immediately | `fly secrets set APPLYFIRST_DAILY_TAILOR_CAP=0 -a <app>` | Every alert is marked `capped` and **no email is sent at all**. Cached packages still send |
| Stop AI spend but keep delivering | `fly secrets set APPLYFIRST_AI_OFF_OK=1 --stage -a <app>`, then `fly secrets unset GEMINI_API_KEY -a <app>` | Users still get an email, containing their own standard message and blank screening answers, with an "AI unavailable" line. Staging the first setting means one restart carries both, so nothing pages in between. Without it `/health` goes 503 and stays there, which would hide a dead worker behind it. To bring the AI back, `fly secrets set GEMINI_API_KEY=... --stage -a <app>`, then `fly secrets unset APPLYFIRST_AI_OFF_OK -a <app>` |
| Stop the confetti download | `CELEBRATE = false` in `_ui.html`, then redeploy | Removes every `data-burst-src`, so the library is never fetched |
| Keep sign-up shut | Leave the Google app in **Testing** | This is the only real gate. `INVITE_ONLY` is only wording |

On Oracle, each of the first two is a line in `/opt/applyfirst/.env` followed by
`sudo systemctl restart applyfirst-saas-web applyfirst-saas-worker` (both: the web pages quote the
daily cap from their own copy of the settings). On Oracle `GEMINI_API_KEY` is **shared with the V1
poller** in the same file, so removing it there also switches V1 to its rules fallback the next
time `applyfirst.service` restarts. To stop only the SaaS's AI spend, leave the key and set
`APPLYFIRST_DAILY_TAILOR_CAP=0` instead (first row).

---

## 4. Restart cleanly

```bash
# Fly
fly apps restart <app>
fly machine restart <machine-id> -a <app>     # id from fly status
```

**Never run `fly scale count` above 1.** A Fly volume attaches to exactly one machine. A second
machine gets its own empty volume and your users split in half.

```bash
# Oracle
sudo systemctl restart applyfirst-saas-worker
sudo systemctl restart applyfirst-saas-web applyfirst-saas-worker

# if it has crash-looped past StartLimitBurst=10 in 300s, clear the latch first
sudo systemctl reset-failed applyfirst-saas-worker
```

---

## 5. Backup and restore

### Take a backup right now

```bash
# Oracle (a timer also does this at 03:00 daily)
sudo systemctl start applyfirst-saas-backup.service
ls -lh /opt/applyfirst/backups/applyfirst-saas-*.db.gz
```

```bash
# Fly (the worker also does this once a day, after its first cycle of each UTC day)
fly ssh console -a <app> -C "python -m applyfirst.saas.backup"
fly ssh console -a <app> -C "ls -lh /data/backups"
fly ssh sftp get /data/backups/<file>.db.gz -a <app>      # pull it OFF the box
```

The daily Fly backup lands on the same volume as the database, so it protects you from a bad write
or a bad deploy, not from losing the volume. That is what pulling a copy off the box is for.

Backups land on the same disk as the database, and the process briefly writes an uncompressed copy
first, which roughly doubles disk use for a moment. On a nearly full volume that is how you fill
it. Keep the last 7, which is the default.

### Restore from a backup

**No restore code or procedure exists in this project.** This sequence is what the code implies.
Practise it once on a throwaway copy before you need it for real.

```bash
# Oracle
sudo systemctl stop applyfirst-saas-web applyfirst-saas-worker
ls -lh /opt/applyfirst/backups/applyfirst-saas-*.db.gz
sudo -u applyfirst gunzip -c /opt/applyfirst/backups/applyfirst-saas-<STAMP>.db.gz > /tmp/restored.db

# the sqlite3 CLI is NOT installed by setup.sh, so check it through the venv
sudo -u applyfirst /opt/applyfirst/.venv/bin/python -c \
  "import sqlite3;print(sqlite3.connect('/tmp/restored.db').execute('PRAGMA integrity_check').fetchone())"

cd /opt/applyfirst
sudo -u applyfirst mv applyfirst-saas.db applyfirst-saas.db.broken
sudo -u applyfirst rm -f applyfirst-saas.db-wal applyfirst-saas.db-shm     # MUST delete these
sudo -u applyfirst cp /tmp/restored.db /opt/applyfirst/applyfirst-saas.db

sudo systemctl start applyfirst-saas-web applyfirst-saas-worker
curl -s https://<domain>/health
```

The `-wal` and `-shm` files **must** be deleted. Leave them and SQLite tries to replay a write-ahead
log belonging to the old file.

On Fly the daily backups sit in `/data/backups`, but **there is no tested procedure yet for swapping
one in**, because the database file can only be replaced while nothing has it open, and on a
one-machine app the only shell you get is inside the running machine. Until that is worked out and
practised, recovery on Fly is from a volume snapshot, and the daily backup is the copy you pull off
the box so you have one either way.

```bash
fly volumes list -a <app>
fly volumes snapshots list <volume-id>
fly volumes create af_data_restored --snapshot-id <snap-id> -s 1 -r sin -a <app>
# then destroy the machine and the old volume, point fly.toml's mount at the new volume, re-deploy
```

Fly keeps snapshots 5 days by default, settable from 1 to 60.

### Roll back a bad deploy

```bash
# Fly
fly releases -a <app> --image                 # find the previous image reference
fly deploy -a <app> --image <previous-image-ref>
```

```bash
# Oracle (there is no rollback step, so pin the commit yourself first)
git -C /opt/applyfirst checkout <good-sha>
sudo bash /opt/applyfirst/deploy/oracle/setup.sh
sudo systemctl restart applyfirst-saas-web applyfirst-saas-worker
```

There are no git tags, so releases are only commit SHAs. Note that `db.migrate` refuses to open a
database stamped newer than the code understands and raises at start-up, so rolling back across a
schema change takes the app down rather than corrupting data. Current schema version is 4.

---

## 6. What it costs

| Users | Hosting | AI if everyone maxes out | AI, realistic |
|---|---|---|---|
| 10 | $4.33 | about $8 | about $2 |
| 100 | $4.33 | about $83 | about $17 |
| 1,000 | $4.33 | about $830 | about $166 |
| 10,000 | you cannot reach this, see section 7 | | |

Hosting is one Fly `shared-cpu-1x` 512MB machine at about $4.18 a month running 24 hours a day,
plus $0.15 per GB-month for the volume. Oracle Always Free is $0, but shares a 1 GB box with your
V1 and carries an idle-reclamation policy that this workload could trip.

The AI is Gemini 2.5 Flash at **$0.30 per million input tokens and $2.50 per million output
tokens**, where output includes the model's own hidden reasoning. One application costs roughly
half a US cent to one cent to write.

**Treat these AI figures as the right shape, not the final number.** The fact-check pass found the
underlying token counts understated, so the true cost is somewhat higher. You will know the real
figure within a week of running it.

At ₱199 a month, about $3.16, the margin is comfortable even at the full cap.

### Three cost traps

**Your daily cap of 10 is not 10 API calls.** It reserves 10 *slots* per user per day. One slot can
make up to 2 provider calls because the engine retries twice, and a retried alert can re-tailor for
free in cap terms, so the absolute ceiling is far above what the setting reads.

**Nothing caps total spend.** There is a limit per user and none across all users at once. A bug
that creates work in a loop has no brake.

**The model's thinking is unbounded and billed at the output rate.** The request sets only
`responseMimeType` and `temperature`. There is no thinking budget of any kind. This is the only
genuinely uncapped cost in the system, and you cannot see it.

---

## 7. Where it falls over

Not the database. Not the server. **The worker.**

It searches onlinejobs.ph once per *distinct* watch word across all users, one after another, with
a 1.0 to 2.5 second pause between each. The pauses alone consume the whole 600 second interval at
about 344 words. Adding realistic network time, a cycle overruns its own interval at roughly
**185 distinct words**, or about 102 on the Oracle unit's 330 second interval.

How many users that is depends entirely on overlap. If the average user brings 2 new words it is
about 100 users. If they bring 8 each it is about 25.

**The failure is silent.** Nothing crashes. `run_once` sleeps the full interval *after* the cycle
finishes, so the real cadence becomes cycle time plus interval. Rounds simply get slower while
every page keeps promising "about every 10 minutes".

**There is an earlier spike.** On a word's first ever poll the worker still fetches the detail page
of every job on the results page, about 30 of them, before discarding them. One user adding the
20-word maximum can add about 15 minutes to a single cycle. That can happen on your second user.

**Backlogs are unbounded.** After any outage every pending alert is processed serially in one
cycle, with no per-cycle limit. A thousand pending alerts is over an hour of blocked loop during
which nobody gets anything new.

**onlinejobs.ph asks for 5 seconds between requests.** Their `robots.txt` says `Crawl-delay: 5` and
the worker waits 1.0 to 2.5. Honouring it would roughly halve the capacity above. Ignoring it is
what gets one shared IP blocked, which takes every user dark at once, detected 18 to 30 minutes
later by the dead-man switch.

**SQLite is not the bottleneck** at any scale the worker permits. Measured at about 595 single-row
commits per second, against a read pattern of one small query set per page view.

---

## 8. Known gaps, in rough priority order

- **No restore or rollback procedure** existed before this document. Section 5 is the first one.
- **Account deletion is promised in the privacy policy and has no code.** Every request becomes
  hand-written SQL. Beware that cascades only fire when `PRAGMA foreign_keys` is ON, and the
  `sqlite3` CLI does not set it by default.
- **A wrong master secret breaks every send forever** while `/health` stays 200, no alert fires and
  no log line appears.
- **A suspended Google OAuth client** fails every sign-in with a generic error while every monitor
  stays green.
- **Two tables grow forever.** Nothing ever deletes from `jobs` or `user_job_alerts`. At a plausible
  300 new posts a day that is roughly 940 MB a year against a 1 GB volume.
- **Garbage that still parses defeats the dead-man switch**, because it only trips when zero jobs
  are seen. A captcha page or a redesign that still yields one job link keeps it quiet.
- **A user can activate without connecting Gmail.** Every matching job is then marked skipped,
  permanently, and skipped alerts are never retried.
- **Dependencies are unpinned.** Any rebuild can pull a new major version and break the product
  with no code change.
- **Rate limiting covers only `/auth/*`.** Everything else is unmetered, including `/health`, which
  opens a fresh database connection on every anonymous request.
- **The Oracle web unit is missing `APPLYFIRST_WORKER_INTERVAL=330`**, so pages say "about every
  10 minutes" while the worker runs about every 5.5.

---

## 9. Which one wakes you at 3am

**It used to be a hung worker**, the one failure where every user went dark, nothing self-healed and
every monitor showed green. Since 2026-09-23 the worker ends any cycle that goes 15 minutes without
progress (`worker_stalled`), and `entrypoint.sh` on Fly or `Restart=always` on Oracle starts a
fresh one, so a hang now costs about 15 minutes, not a night.

What is left is a worker that restarts and hangs again every time, or goes blind. Both turn
`/health` 503, so everything can wait until morning without a user noticing, **as long as `/health`
is being watched by something that can wake you.**
