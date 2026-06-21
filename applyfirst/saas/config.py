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
    trust_proxy: bool = True            # read client IP from X-Forwarded-For (Caddy is the only ingress)
    # M5 nightly backup
    backup_dir: str = "backups"
    backup_keep: int = 7
    backup_remote_cmd: str | None = None  # off-box push template; "{path}" → the .db.gz (inert if unset)

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
            "SESSION_SECRET is required when secure cookies are on (production). "
            "Generate one with `openssl rand -base64 32`."
        )

    base_url = os.getenv("APPLYFIRST_BASE_URL", "https://localhost:8000").rstrip("/")

    return SaaSConfig(
        db_path=db_path,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or None,
        session_secret=session_secret,
        base_url=base_url,
        secure_cookies=secure,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        daily_tailor_cap=int(os.getenv("APPLYFIRST_DAILY_TAILOR_CAP") or "10"),
        worker_interval=int(os.getenv("APPLYFIRST_WORKER_INTERVAL") or "600"),
        worker_jitter=float(os.getenv("APPLYFIRST_WORKER_JITTER") or "0.25"),
        owner_alert_email=os.getenv("APPLYFIRST_OWNER_EMAIL") or None,
        smtp_host=os.getenv("APPLYFIRST_SMTP_HOST") or None,
        smtp_port=int(os.getenv("APPLYFIRST_SMTP_PORT") or "465"),
        smtp_user=os.getenv("APPLYFIRST_SMTP_USER") or None,
        smtp_password=os.getenv("APPLYFIRST_SMTP_PASSWORD") or None,
        alert_webhook_url=os.getenv("APPLYFIRST_ALERT_WEBHOOK") or None,
        auth_rate_limit=int(os.getenv("APPLYFIRST_AUTH_RATE_LIMIT") or "20"),
        auth_rate_window=int(os.getenv("APPLYFIRST_AUTH_RATE_WINDOW") or "60"),
        trust_proxy=_as_bool(os.getenv("APPLYFIRST_TRUST_PROXY"), default=True),
        backup_dir=os.getenv("APPLYFIRST_BACKUP_DIR") or "backups",
        backup_keep=int(os.getenv("APPLYFIRST_BACKUP_KEEP") or "7"),
        backup_remote_cmd=os.getenv("APPLYFIRST_BACKUP_REMOTE") or None,
    )
