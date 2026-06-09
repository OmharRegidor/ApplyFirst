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
[[ -f "$APP_DIR/.env" ]] && chmod 600 "$APP_DIR/.env" || true

echo "==> Installing systemd units"
install -m 644 "$APP_DIR/deploy/oracle/applyfirst.service"        /etc/systemd/system/applyfirst.service
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-health.service" /etc/systemd/system/applyfirst-health.service
install -m 644 "$APP_DIR/deploy/oracle/applyfirst-health.timer"   /etc/systemd/system/applyfirst-health.timer
systemctl daemon-reload

cat <<EOF

==> Provisioning done.

Next (one time), create your two private files in $APP_DIR (NOT committed):
  1. .env          — copy .env.example, fill in SMTP + GEMINI_API_KEY + keywords
  2. profile.yaml  — copy profile.example.yaml, fill in your resume
     (or 'scp' the ones from your laptop straight into $APP_DIR/)

  sudo install -o $APP_USER -g $APP_USER -m 600 /path/to/.env        $APP_DIR/.env
  sudo install -o $APP_USER -g $APP_USER -m 644 /path/to/profile.yaml $APP_DIR/profile.yaml

Then start it:
  sudo systemctl enable --now applyfirst.service
  sudo systemctl enable --now applyfirst-health.timer

Verify:
  systemctl status applyfirst.service
  journalctl -u applyfirst -f
EOF
