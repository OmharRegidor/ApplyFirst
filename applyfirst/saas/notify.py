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
    return deliver(cfg, subject, body) is not None


def deliver(cfg, subject: str, body: str) -> str | None:
    """Try the webhook, then SMTP. Return the name of the channel that accepted the alert, or
    None when it fell back to the log. Never raises."""
    text = f"{subject}\n\n{body}"

    if cfg.alert_webhook_url:
        import httpx
        try:
            # {"text", "content"} covers both Slack (text) and Discord (content); each
            # service ignores the field it doesn't use.
            resp = httpx.post(cfg.alert_webhook_url, json={"text": text, "content": text}, timeout=10)
            # A mistyped or revoked webhook answers 4xx. That is not delivered, so fall through
            # to SMTP and the log rather than report success.
            resp.raise_for_status()
            return "webhook"
        except httpx.HTTPStatusError as exc:
            # Only the status. The webhook URL works like a password and the error text carries it.
            log.event(_LOG, "owner_alert_webhook_failed", level=logging.ERROR,
                      status=exc.response.status_code)
        except Exception as exc:  # noqa: BLE001 — alerting must never propagate
            log.event(_LOG, "owner_alert_webhook_failed", level=logging.ERROR,
                      error=str(exc).replace(cfg.alert_webhook_url, "<webhook>")[:200])

    if cfg.smtp_host and cfg.smtp_user and cfg.smtp_password and cfg.owner_alert_email:
        try:
            from applyfirst.notify.email_smtp import SmtpNotifier
            SmtpNotifier(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user, cfg.smtp_password,
                         sender=cfg.smtp_user, recipient=cfg.owner_alert_email).send(subject, body)
            return "smtp"
        except Exception as exc:  # noqa: BLE001
            log.event(_LOG, "owner_alert_smtp_failed", level=logging.ERROR, error=str(exc)[:200])

    # No channel configured (or all failed) — surface it loudly in the logs.
    log.event(_LOG, "owner_alert_logonly", level=logging.CRITICAL, subject=subject)
    return None


def main(argv: list[str] | None = None) -> int:
    """Send one test alert, so the owner can see it arrive.

        python -m applyfirst.saas.notify --test
        fly ssh console -a <app> -C "python -m applyfirst.saas.notify --test"

    Exit 0 only when the configured first channel delivered it. A broken webhook that fell back
    to SMTP still exits 1, because the channel you meant to use is not working.
    """
    import argparse

    from applyfirst.saas.config import load_saas_config

    parser = argparse.ArgumentParser(prog="applyfirst.saas.notify")
    parser.add_argument("--test", action="store_true", help="send one test alert and exit")
    args = parser.parse_args(argv)
    if not args.test:
        parser.print_help()
        return 2
    cfg = load_saas_config()
    log.configure(cfg.log_json, cfg.log_level)
    wanted = cfg.alert_channel
    got = deliver(cfg, "Agad test alert",
                  "If you can read this, owner alerts reach you. Nothing is wrong.")
    print(f"configured: {wanted or 'none'}, delivered by: {got or 'nothing'}")
    if got and got != wanted:
        print(f"{wanted} failed, so the alert went by {got}. Fix {wanted} or remove it.")
    return 0 if got and got == wanted else 1


if __name__ == "__main__":
    raise SystemExit(main())
