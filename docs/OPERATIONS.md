# Running Agad in production

What the backend really does, what it costs, what breaks, and exactly what you type when it does.

Written 2026-09-21 from the code itself, with every claim checked against a file and line, and the
money and downtime claims checked a second time by a separate pass. Prices were read from the
vendors' own pages on that date, so re-check them before you rely on them.

**Status when this was written.** V2 has never been deployed anywhere. No Fly app, no Google OAuth
client, no real user. Every number below comes from reading the code and the vendor docs, never
from watching it run in production. Your first deploy is also your first real measurement.

---

## 1. Before you launch, six things that are not built

Following the current deploy runbook exactly would ship a product with the AI switched off, no
working logs, no alert reaching you, no backups, and nothing to restart the worker when it stops.
None of these are hard. All of them are missing.

| # | What is wrong | Why it matters | Smallest fix |
|---|---|---|---|
| 1 | The Gemini key is in neither `fly.toml` nor the deploy steps, and is commented out in `deploy/oracle/saas-env.sample` | With no provider the engine uses the rules fallback, so your first user gets their own unchanged message plus the line "(AI unavailable — answers are blank; edit before sending.)" | `fly secrets set GEMINI_API_KEY=... -a <app>` |
| 2 | Application logging is never switched on in the SaaS. `log.configure()` is called only by the V1 CLI (`applyfirst/cli.py:101`, `:131`) | Every structured event is thrown away. `journalctl ... \| grep worker_blind` returns nothing even when the worker IS blind. Both runbooks tell you to read logs that do not exist | Call `log.configure()` at SaaS start-up |
| 3 | No alert destination is configured. `fly.toml` sets no webhook, no SMTP, no owner email | The dead-man switch fires into a log nobody reads | `fly secrets set APPLYFIRST_ALERT_WEBHOOK=<slack-or-discord-url>` |
| 4 | **The Fly worker watchdog is dead code.** `entrypoint.sh:104` runs `( wait "$worker_pid"; ...; kill 1 ) &`, but the worker is a sibling of that subshell, not a child, so `wait` errors immediately and `set -eu` kills the subshell before `kill 1` ever runs | On Fly, a worker that **crashes** is never restarted either, not just one that hangs. Fly's own check points at `/healthz`, which is a constant "ok", so the machine looks perfectly healthy while every user goes dark | Use Fly `[processes]` or fix the wait, and point an uptime monitor at `/health` |
| 5 | Nothing ever runs a backup on Fly. `entrypoint.sh` starts only the worker and uvicorn, and `fly.toml` has no process or cron stanza, while `fly.toml:12` sets `APPLYFIRST_BACKUP_DIR` so it *looks* configured | Your only Fly safety net is Fly's own volume snapshot, kept 5 days, which you have never restored | Schedule `python -m applyfirst.saas.backup`, and practise section 5 once |
| 6 | Google forces a 7-day refresh-token expiry while the app is unverified, and the code clears the credential silently | Every beta user stops receiving anything once a week and is told nothing. They only find out if they happen to open the dashboard | Send a "reconnect Gmail" email via the existing `notify.py` SMTP path when the credential is cleared |

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

**Read `/health` properly.** It returns 503 only when the worker heartbeat is older than
2.5 times the poll interval, which is 25 minutes at the 600 second default. It reports
`"db": "ok"` as a hardcoded string, so it tells you nothing about the database. If the database
file is actually corrupt, `/health` returns **500**, not 503, and so does every page on the site,
while `/healthz` keeps saying "ok".

**Put an uptime monitor on `/health`.** It is the only automatic way you will ever learn that the
worker has stopped. Nothing else notices.

---

## 3. Stop the bleeding

Four switches that already exist. Know them before you need them.

| Goal | Do this | What actually happens |
|---|---|---|
| Stop all AI spend immediately | `fly secrets set APPLYFIRST_DAILY_TAILOR_CAP=0 -a <app>` | Every alert is marked `capped` and **no email is sent at all**. Cached packages still send |
| Stop AI spend but keep delivering | `fly secrets unset GEMINI_API_KEY -a <app>` | Users still get an email, containing their own standard message and blank screening answers, with an "AI unavailable" line |
| Stop the confetti download | `CELEBRATE = false` in `_ui.html`, then redeploy | Removes every `data-burst-src`, so the library is never fetched |
| Keep sign-up shut | Leave the Google app in **Testing** | This is the only real gate. `INVITE_ONLY` is only wording |

On Oracle, each of the first two is a line in `/opt/applyfirst/.env` followed by
`sudo systemctl restart applyfirst-saas-worker`.

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
# Fly (nothing is scheduled, so this is the only way)
fly ssh console -a <app> -C "python -m applyfirst.saas.backup"
fly ssh sftp get /data/backups/<file>.db.gz -a <app>      # pull it OFF the box
```

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

On Fly there are no local backups, so recovery is from a volume snapshot.

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

**A hung worker.** It is the only failure where every user goes dark, nothing self-heals, and every
monitor you have shows green. On Fly the restart watchdog does not work at all. On Oracle the
health watchdog restarts the V1 poller, not the SaaS worker.

Everything else can wait until morning without a user noticing, as long as `/health` is being
watched by something that can wake you.
