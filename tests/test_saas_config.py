"""M5 — config loading is robust to empty-string env vars (don't crash on `VAR=`)."""

from __future__ import annotations

from applyfirst.saas.config import load_saas_config


def test_empty_numeric_env_vars_fall_back_to_defaults(monkeypatch):
    # isolate from any real .env on disk
    monkeypatch.setattr("applyfirst.saas.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("APPLYFIRST_SAAS_SECURE_COOKIES", "0")   # avoid the prod SESSION_SECRET guard
    for var in ("APPLYFIRST_SMTP_PORT", "APPLYFIRST_AUTH_RATE_LIMIT",
                "APPLYFIRST_AUTH_RATE_WINDOW", "APPLYFIRST_BACKUP_KEEP",
                "APPLYFIRST_WORKER_INTERVAL", "APPLYFIRST_WORKER_JITTER",
                "APPLYFIRST_DAILY_TAILOR_CAP"):
        monkeypatch.setenv(var, "")   # explicitly empty — must NOT raise ValueError

    cfg = load_saas_config()
    assert cfg.smtp_port == 465
    assert cfg.auth_rate_limit == 20 and cfg.auth_rate_window == 60
    assert cfg.worker_interval == 600 and cfg.worker_jitter == 0.25
    assert cfg.backup_keep == 7 and cfg.daily_tailor_cap == 10
