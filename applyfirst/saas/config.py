"""SaaS configuration — loaded from environment / a local .env file.

Kept separate from ``applyfirst.config`` (the CLI's settings) so the two apps never
share a database file or leak each other's settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _filled(name: str) -> str | None:
    """An environment value, or None when it is empty or still a template placeholder such as
    ``<your-gemini-key>`` or ``...``. A copied-but-unfilled sample line must read as missing, or
    it would quietly switch off the warnings that exist to catch exactly that."""
    value = (os.getenv(name) or "").strip()
    if not value or value == "..." or (value.startswith("<") and value.endswith(">")):
        return None
    return value


# The CLI's database file — the SaaS must NEVER point at it (R4 in the M1 plan).
_CLI_DB_NAMES = ("applyfirst.db",)


@dataclass(slots=True)
class SaaSConfig:
    db_path: str
    google_client_id: str | None
    google_client_secret: str | None
    session_secret: bytes
    base_url: str          # e.g. "https://localhost:8000" (no trailing slash)
    secure_cookies: bool   # True in prod → __Host- cookies; False for http dev/tests
    # M3 worker
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    daily_tailor_cap: int = 10          # per-user tailoring calls/day
    worker_interval: int = 600          # seconds between poll cycles
    worker_jitter: float = 0.25         # ± fraction of the interval (two-sided)
    # M5 owner alerting (dead-man's switch → the OWNER, never tenants). Prefer a webhook;
    # else SMTP; else log-only. Supply ONE channel — all are optional/default-safe.
    owner_alert_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    alert_webhook_url: str | None = None
    # M5 /auth/* rate limiting (DB-backed fixed window, shared across uvicorn workers)
    auth_rate_limit: int = 20           # max /auth/* requests per IP per window (0 disables)
    auth_rate_window: int = 60          # window length, seconds
    trust_proxy: bool = True            # trust a proxy-set client-IP header (see trusted_ip_header)
    # Which proxy header carries the real client IP for the rate limiter. Fly.io: "fly-client-ip"
    # (Fly Proxy sets it from the real TCP peer — not client-forgeable). Unset (None) → take the
    # LAST X-Forwarded-For hop, correct for a reverse proxy that appends the real peer (Caddy on
    # the Oracle VM). Never key on the FIRST XFF hop — it is client-forgeable.
    trusted_ip_header: str | None = None
    # M5 nightly backup
    backup_dir: str = "backups"
    backup_keep: int = 7
    backup_remote_cmd: str | None = None  # off-box push template; "{path}" → the .db.gz (inert if unset)
    # The worker takes the day's backup itself after its first cycle of each UTC day. For hosts
    # with no scheduler of their own (Fly). Leave it off where a timer already does it (Oracle).
    backup_in_worker: bool = False
    # Logging. The SaaS prints nothing for humans, so its structured events ARE its logs: on by
    # default, one JSON object per line on stderr, which Fly logs and journald both collect.
    log_json: bool = True
    log_level: str = "INFO"
    # Worker self-watchdog: a cycle that makes no progress (no keyword polled, no alert handled)
    # for this long is treated as hung, and the worker exits so its supervisor starts a fresh one.
    worker_stall_seconds: int = 900
    # The owner switched the AI off on purpose (to stop spend, say). The missing credential then
    # stops paging through /health and the start-up alert, so the one monitor stays free to
    # report a dead or blind worker.
    ai_off_ok: bool = False

    @property
    def is_production(self) -> bool:
        """Secure cookies are on only in a real deployment (tests and http dev turn them off)."""
        return self.secure_cookies

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def alert_channel(self) -> str | None:
        """The owner-alert channel ``notify.send_owner_alert`` would try first, or None."""
        if self.alert_webhook_url:
            return "webhook"
        if self.smtp_host and self.smtp_user and self.smtp_password and self.owner_alert_email:
            return "smtp"
        return None

    @property
    def redirect_uri(self) -> str:
        return f"{self.base_url}/auth/callback"

    @property
    def gmail_redirect_uri(self) -> str:
        return f"{self.base_url}/auth/gmail-callback"


def load_saas_config() -> SaaSConfig:
    """Build a SaaSConfig from the environment, failing loudly on unsafe combos."""
    load_dotenv()

    db_path = os.getenv("APPLYFIRST_SAAS_DB", "applyfirst-saas.db")
    if os.path.basename(db_path) in _CLI_DB_NAMES:
        raise RuntimeError(
            "APPLYFIRST_SAAS_DB must not collide with the CLI database "
            f"({_CLI_DB_NAMES[0]}) — pick a distinct file like applyfirst-saas.db."
        )

    secure = _as_bool(os.getenv("APPLYFIRST_SAAS_SECURE_COOKIES"), default=True)

    secret_raw = os.getenv("SESSION_SECRET")
    if secret_raw:
        session_secret = secret_raw.encode("utf-8")
    elif not secure:
        # http dev / tests only — never reached in prod (secure_cookies is True there).
        session_secret = b"dev-insecure-session-secret-do-not-use-in-prod"
    else:
        raise RuntimeError(
            "SESSION_SECRET is required when secure cookies are on (production). Generate one with: "
            'python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"'
        )

    base_url_raw = os.getenv("APPLYFIRST_BASE_URL")
    if secure and (not base_url_raw or "localhost" in base_url_raw or "127.0.0.1" in base_url_raw):
        raise RuntimeError(
            "APPLYFIRST_BASE_URL must be your public https URL (e.g. https://<name>.fly.dev) in "
            "production (secure cookies on). It builds the Google OAuth redirect_uri; a localhost/"
            "default value causes redirect_uri_mismatch and 100% sign-in failure."
        )
    base_url = (base_url_raw or "https://localhost:8000").rstrip("/")

    return SaaSConfig(
        db_path=db_path,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or None,
        session_secret=session_secret,
        base_url=base_url,
        secure_cookies=secure,
        gemini_api_key=_filled("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        daily_tailor_cap=int(os.getenv("APPLYFIRST_DAILY_TAILOR_CAP") or "10"),
        worker_interval=int(os.getenv("APPLYFIRST_WORKER_INTERVAL") or "600"),
        worker_jitter=float(os.getenv("APPLYFIRST_WORKER_JITTER") or "0.25"),
        owner_alert_email=_filled("APPLYFIRST_OWNER_EMAIL"),
        smtp_host=_filled("APPLYFIRST_SMTP_HOST"),
        smtp_port=int(os.getenv("APPLYFIRST_SMTP_PORT") or "465"),
        smtp_user=_filled("APPLYFIRST_SMTP_USER"),
        smtp_password=_filled("APPLYFIRST_SMTP_PASSWORD"),
        alert_webhook_url=_filled("APPLYFIRST_ALERT_WEBHOOK"),
        auth_rate_limit=int(os.getenv("APPLYFIRST_AUTH_RATE_LIMIT") or "20"),
        auth_rate_window=int(os.getenv("APPLYFIRST_AUTH_RATE_WINDOW") or "60"),
        trust_proxy=_as_bool(os.getenv("APPLYFIRST_TRUST_PROXY"), default=True),
        trusted_ip_header=os.getenv("APPLYFIRST_TRUSTED_IP_HEADER") or None,
        backup_dir=os.getenv("APPLYFIRST_BACKUP_DIR") or "backups",
        backup_keep=int(os.getenv("APPLYFIRST_BACKUP_KEEP") or "7"),
        backup_remote_cmd=os.getenv("APPLYFIRST_BACKUP_REMOTE") or None,
        backup_in_worker=_as_bool(os.getenv("APPLYFIRST_BACKUP_IN_WORKER")),
        log_json=_as_bool(os.getenv("APPLYFIRST_LOG_JSON") or None, default=True),   # empty = default
        log_level=os.getenv("APPLYFIRST_LOG_LEVEL") or "INFO",
        worker_stall_seconds=int(os.getenv("APPLYFIRST_WORKER_STALL_SECONDS") or "900"),
        ai_off_ok=_as_bool(os.getenv("APPLYFIRST_AI_OFF_OK")),
    )


# Consecutive cycles in which onlinejobs.ph returned no jobs at all before the worker is called
# blind. Shared by the worker (owner alert) and /health (503), so both trip on the same cycle.
DEADMAN_THRESHOLD = 3
