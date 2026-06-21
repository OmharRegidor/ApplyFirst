#!/usr/bin/env bash
# ApplyFirst — Oracle Cloud (Ubuntu, ARM or x86) provisioning script.
# Idempotent: safe to re-run (it updates code + deps and reinstalls the units).
#
#   sudo bash setup.sh
#
# It does NOT create .env or profile.yaml (those hold your secrets/resume) and does
# NOT start the service — you do that after dropping those two files in (see README.md).
set -euo pipefail

APP_DIR=/opt/applyfirst
APP_USER=applyfirst
REPO_URL="${APPLYFIRST_REPO_URL:-https://github.com/OmharRegidor/ApplyFirst.git}"

if [[ $EUID -ne 0 ]]; then
    echo "Please run as root:  sudo bash setup.sh" >&2
    exit 1
fi

echo "==> Installing OS packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git build-essential

# Caddy — auto-HTTPS reverse proxy for the V2 SaaS (skipped if already present).
if ! command -v caddy >/dev/null 2>&1; then
    echo "==> Installing Caddy (SaaS HTTPS reverse proxy)"
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -y
    apt-get install -y caddy
fi

echo "==> Creating system user '$APP_USER'"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

echo "==> Fetching the code into $APP_DIR"
if [[ -d "$APP_DIR/.git" ]]; then
    git -C "$APP_DIR" pull --ff-only
else
    # Dir may already exist (created as the user's home). Clone into it if empty of code.
    if [[ -f "$APP_DIR/requirements.txt" ]]; then
        echo "    (code already present, not a git checkout — leaving as-is)"
    else
        git clone "$REPO_URL" "$APP_DIR.tmp"
        cp -a "$APP_DIR.tmp/." "$APP_DIR/"
        rm -rf "$APP_DIR.tmp"
    fi
fi

echo "==> Creating the virtualenv + installing dependencies"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

echo "==> Fixing ownership + permissions"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod +x "$APP_DIR/deploy/oracle/health-check.sh"
chmod +x "$APP_DIR/deploy/oracle/saas-backup.sh"
[[ -f "$APP_DIR/.env" ]] && chmod 600 "$APP_DIR/.env" || true

echo "==> Installing systemd units"
# V1 CLI (poller + self-healing watchdog)
install -m 644 "$APP_DIR/deploy/oracle/applyfirst.service"        /etc/systemd/system/applyfirst.service
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-health.service" /etc/systemd/system/applyfirst-health.service
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-health.timer"   /etc/systemd/system/applyfirst-health.timer
# V2 SaaS (web + worker + nightly backup)
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-saas-web.service"     /etc/systemd/system/applyfirst-saas-web.service
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-saas-worker.service"  /etc/systemd/system/applyfirst-saas-worker.service
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-saas-backup.service"  /etc/systemd/system/applyfirst-saas-backup.service
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-saas-backup.timer"    /etc/systemd/system/applyfirst-saas-backup.timer
systemctl daemon-reload

echo "==> Installing the Caddyfile"
install -d -m 755 /etc/caddy
install -m 644 "$APP_DIR/deploy/oracle/Caddyfile" /etc/caddy/Caddyfile
# Pick up Caddyfile changes on a re-run; harmless if Caddy isn't started yet (first provision).
systemctl reload caddy 2>/dev/null || true

cat <<EOF

==> Provisioning done.

Next (one time), create your two private files in $APP_DIR (NOT committed):
  1. .env          — copy .env.example, fill in SMTP + GEMINI_API_KEY + keywords
  2. profile.yaml  — copy profile.example.yaml, fill in your resume
     (or 'scp' the ones from your laptop straight into $APP_DIR/)

  sudo install -o $APP_USER -g $APP_USER -m 600 /path/to/.env        $APP_DIR/.env
  sudo install -o $APP_USER -g $APP_USER -m 644 /path/to/profile.yaml $APP_DIR/profile.yaml

Then start the V1 CLI poller:
  sudo systemctl enable --now applyfirst.service
  sudo systemctl enable --now applyfirst-health.timer

Verify:
  systemctl status applyfirst.service
  journalctl -u applyfirst -f

------------------------------------------------------------------------------
V2 SaaS (optional — see README.md "Deploying the V2 SaaS"):
  1. Add the SaaS keys to $APP_DIR/.env (GOOGLE_CLIENT_ID/SECRET, SESSION_SECRET,
     APPLYFIRST_BASE_URL=https://<domain>, APPLYFIRST_SAAS_DB=applyfirst-saas.db,
     the master key, and ONE owner-alert channel) — then re-run 'chmod 600 .env'.
  2. Point your domain's A-record at this VM and open ports 80/443.
  3. Tell Caddy your domain (e.g. add APPLYFIRST_DOMAIN=apply.example.com to
     /etc/default/caddy), then: sudo systemctl reload caddy
  4. Start the units:
       sudo systemctl enable --now applyfirst-saas-web applyfirst-saas-worker
       sudo systemctl enable --now applyfirst-saas-backup.timer
  5. Verify:  curl -s https://<domain>/health   (200 = ready; 503 = worker stale)
EOF
