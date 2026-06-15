# Deploying ApplyFirst on an Oracle Cloud Always-Free VM

A 24/7, $0 home for the continuous `run` loop. The app is **outbound-only** (it scrapes
onlinejobs.ph, sends Gmail SMTP, and calls Gemini) — so **no inbound ports are needed**
beyond SSH. State is a local SQLite file; nothing external to manage.

What you'll end up with:
- `applyfirst.service` — the poll loop, auto-restarted on crash (`Restart=always`).
- `applyfirst-health.timer` — every 10 min, restarts the loop if its heartbeat goes stale
  (catches a *hung* loop, which crash-restart can't).
- Daily local SQLite backups (the loop does this itself, once per UTC day, in `backups/`).
- Structured JSON logs in journald (`APPLYFIRST_LOG_JSON=1`).

---

## 1. Create the VM (Oracle Cloud Console)

1. **Sign up** at https://www.oracle.com/cloud/free/ (needs a card for ID verification — ~$1 hold, refunded). Pick a home region close to you.
2. **Compute → Instances → Create instance:**
   - **Image:** Canonical Ubuntu 22.04 or 24.04.
   - **Shape:** `VM.Standard.A1.Flex` (Ampere **ARM**, Always Free — 1 OCPU / 6 GB is plenty).
     *If ARM capacity is unavailable, retry later / another AD, or use `VM.Standard.E2.1.Micro` (AMD, also Always Free).*
   - **SSH keys:** upload your public key (or let it generate one — save the private key).
   - Networking: leave defaults. **Do not add any ingress rules** — the app needs none.
3. Create, then note the **public IP**.

## 2. SSH in
```bash
ssh ubuntu@<PUBLIC_IP>          # Ubuntu images log in as 'ubuntu'
```

## 3. Provision
```bash
# grab just the deploy script (or clone the whole repo)
sudo apt-get update -y && sudo apt-get install -y git
git clone https://github.com/OmharRegidor/ApplyFirst.git /tmp/applyfirst-src
sudo bash /tmp/applyfirst-src/deploy/oracle/setup.sh
```
`setup.sh` installs Python + deps, creates the `applyfirst` system user, puts the code in
`/opt/applyfirst`, builds the venv, and installs (but does not start) the systemd units.

## 4. Drop in your two private files (NOT in git)

Easiest — copy the ones from your laptop:
```bash
# from your LAPTOP (PowerShell/terminal), in the project folder:
scp .env         ubuntu@<PUBLIC_IP>:/tmp/.env
scp profile.yaml ubuntu@<PUBLIC_IP>:/tmp/profile.yaml

# then on the VM:
sudo install -o applyfirst -g applyfirst -m 600 /tmp/.env         /opt/applyfirst/.env
sudo install -o applyfirst -g applyfirst -m 644 /tmp/profile.yaml /opt/applyfirst/profile.yaml
rm /tmp/.env /tmp/profile.yaml
```
(Or `sudo -u applyfirst nano /opt/applyfirst/.env` and paste, starting from `.env.example`.)
**`.env` must be mode 600** — it holds your SMTP App Password and Gemini key.

## 5. Start it
```bash
sudo systemctl enable --now applyfirst.service
sudo systemctl enable --now applyfirst-health.timer
```

## 6. Verify
```bash
systemctl status applyfirst.service          # should be "active (running)"
journalctl -u applyfirst -f                   # live logs (Ctrl-C to stop watching)
sudo -u applyfirst /opt/applyfirst/.venv/bin/python -m applyfirst.cli health   # exit 0 once the first cycle ran
sudo -u applyfirst /opt/applyfirst/.venv/bin/python -m applyfirst.cli list      # jobs caught so far
```
The first cycle **baselines your keywords silently** (no email). New posts after that
trigger alerts to `ALERT_TO`.

---

## Day-2 operations

| Task | Command |
|---|---|
| Live logs | `journalctl -u applyfirst -f` |
| JSON events only | `journalctl -u applyfirst -o cat \| grep '^{'` |
| Health (exit 1 = stale) | `sudo -u applyfirst /opt/applyfirst/.venv/bin/python -m applyfirst.cli health` |
| Manual backup | `sudo -u applyfirst /opt/applyfirst/.venv/bin/python -m applyfirst.cli backup` |
| Backups on disk | `ls -lh /opt/applyfirst/backups/` |
| Restart | `sudo systemctl restart applyfirst.service` |
| Stop | `sudo systemctl disable --now applyfirst.service applyfirst-health.timer` |
| Update to latest code | `sudo bash /opt/applyfirst/deploy/oracle/setup.sh && sudo systemctl restart applyfirst.service` |
| Change keywords/interval | edit `/opt/applyfirst/.env`, then `sudo systemctl restart applyfirst.service` |

### Watchdog from outside the box (optional)
The internal timer restarts a hung loop. To also be alerted if the **whole VM** dies, point a
free https://uptimerobot.com "heartbeat" monitor at a tiny cron that curls UptimeRobot only
when `health` passes — ping me and I'll add that.

### Security notes
- `.env` is mode 600, owned by `applyfirst`; the service runs unprivileged with
  `ProtectSystem`/`ProtectHome`/`NoNewPrivileges`.
- No inbound ports are opened. Keep the VM patched: `sudo apt-get update && sudo apt-get upgrade -y`.
- Rotate the Gmail App Password + Gemini key if they were ever shared in plaintext; update `.env` and restart.

### Troubleshooting
- **`active (running)` but no alerts:** expected at first — the first poll is a silent baseline.
  Watch `journalctl -u applyfirst -f` over the next interval for `new=` > 0.
- **AI answers look generic / `rules-fallback`:** the Gemini key is out of quota (HTTP 429) or unset;
  the app degrades to rules-based answers. Check quota at https://ai.dev/rate-limit.
- **Service keeps restarting:** `journalctl -u applyfirst -n 50` — usually a bad `.env`
  (missing SMTP creds with `EMAIL_ENABLED=true`) or no network egress.

---

## Optional — the read-only web dashboard (private, via Tailscale)

`applyfirst.web` is a tiny FastAPI dashboard to browse caught jobs and their AI-tailored
packages from your phone/laptop. It is **read-only** (opens the DB with `query_only=ON`) and is
reached **privately over Tailscale**. It binds to all interfaces, but the OCI security list opens
**only port 22**, so `:8000` is **never** exposed to the public internet — it is reachable only via
the private tailnet (and localhost). No new inbound ports are opened.

### 1. Install dependencies + the unit (on the VM)
```bash
# pulls fastapi/uvicorn/jinja2 from requirements.txt and installs the new unit
sudo bash /opt/applyfirst/deploy/oracle/setup.sh
sudo install -m 644 /opt/applyfirst/deploy/oracle/applyfirst-dash.service /etc/systemd/system/applyfirst-dash.service
sudo systemctl daemon-reload
```

### 2. Install Tailscale (one-time, interactive)
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up        # prints a URL — open it in your browser and approve the device
tailscale ip -4          # note the 100.x.y.z address (or use the MagicDNS name: 'applyfirst')
```
Install the **Tailscale app** on your phone/laptop and sign in with the **same account**.

### 3. Start the dashboard
```bash
sudo systemctl enable --now applyfirst-dash.service
systemctl status applyfirst-dash.service     # active (running)
curl -s localhost:8000/healthz               # -> ok
```

### 4. Open it
From any device on your tailnet: **`http://applyfirst:8000`** (MagicDNS) or `http://100.x.y.z:8000`.

> The dashboard shows the package only for jobs caught **after** it was deployed (the poller
> persists each package at send time). Older jobs show "emailed only — check your inbox."

| Task | Command |
|---|---|
| Dashboard logs | `journalctl -u applyfirst-dash -f` |
| Restart dashboard | `sudo systemctl restart applyfirst-dash.service` |
| Stop dashboard | `sudo systemctl disable --now applyfirst-dash.service` |
| Confirm caps | `systemctl show applyfirst-dash -p MemoryMax -p CPUQuota` |
