"""Owner alerting for the SaaS (M5) — webhook, else SMTP, else log-only.

The worker has no send path of its own: ``gmail_send`` is tenant-bound (it sends FROM/TO
a user's own inbox using that user's refresh token). So the dead-man's switch needs a
separate, server-owned transport to reach the OWNER. This module is that transport.

Pluggable + default-safe: the owner supplies ONE channel via the SaaS ``.env``. If none is
configured, alerts degrade to a CRITICAL log line. ``send_owner_alert`` NEVER raises — a
failed alert must not crash the worker.
"""

from __future__ import annotations

import logging

from applyfirst import log

_LOG = log.get_logger("saas.notify")


def send_owner_alert(cfg, subject: str, body: str) -> bool:
    """Best-effort owner alert. Returns True if a channel accepted it, else False."""
    text = f"{subject}\n\n{body}"

    if cfg.alert_webhook_url:
        try:
            import httpx
            # {"text", "content"} covers both Slack (text) and Discord (content); each
            # service ignores the field it doesn't use.
            httpx.post(cfg.alert_webhook_url, json={"text": text, "content": text}, timeout=10)
            return True
        except Exception as exc:  # noqa: BLE001 — alerting must never propagate
            log.event(_LOG, "owner_alert_webhook_failed", level=logging.ERROR, error=str(exc)[:200])

    if cfg.smtp_host and cfg.smtp_user and cfg.smtp_password and cfg.owner_alert_email:
        try:
            from applyfirst.notify.email_smtp import SmtpNotifier
            SmtpNotifier(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user, cfg.smtp_password,
                         sender=cfg.smtp_user, recipient=cfg.owner_alert_email).send(subject, body)
            return True
        except Exception as exc:  # noqa: BLE001
            log.event(_LOG, "owner_alert_smtp_failed", level=logging.ERROR, error=str(exc)[:200])

    # No channel configured (or all failed) — surface it loudly in the logs.
    log.event(_LOG, "owner_alert_logonly", level=logging.CRITICAL, subject=subject)
    return False
