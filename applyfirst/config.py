"""Settings loaded from environment / a local .env file.

Secrets (email app password, Gemini key, etc.) live in .env which is git-ignored.
CLI flags override these where provided.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(slots=True)
class Settings:
    db: str = "applyfirst.db"
    poll_interval: int = 300
    keywords: list[str] = field(default_factory=list)
    profile_path: str = "profile.yaml"
    # email
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    alert_from: str | None = None
    alert_to: str | None = None
    # AI
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    # observability
    log_json: bool = False
    log_level: str = "INFO"


def load_settings() -> Settings:
    load_dotenv()  # reads ./.env if present; no-op otherwise
    raw_keywords = os.getenv("APPLYFIRST_KEYWORDS", "")
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
    return Settings(
        db=os.getenv("APPLYFIRST_DB", "applyfirst.db"),
        poll_interval=int(os.getenv("APPLYFIRST_POLL_INTERVAL_SECONDS", "300")),
        keywords=keywords,
        profile_path=os.getenv("APPLYFIRST_PROFILE", "profile.yaml"),
        email_enabled=_as_bool(os.getenv("EMAIL_ENABLED")),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        smtp_user=os.getenv("SMTP_USER") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        alert_from=os.getenv("ALERT_FROM") or None,
        alert_to=os.getenv("ALERT_TO") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        log_json=_as_bool(os.getenv("APPLYFIRST_LOG_JSON")),
        log_level=os.getenv("APPLYFIRST_LOG_LEVEL", "INFO"),
    )
