"""M5 — owner-alert transport: webhook → SMTP → log-only, never raises."""

from __future__ import annotations

import dataclasses

from applyfirst.saas import notify


def test_webhook_used_when_configured(saas_cfg, monkeypatch):
    cfg = dataclasses.replace(saas_cfg, alert_webhook_url="https://hook.example/x")
    captured = {}

    import httpx
    monkeypatch.setattr(httpx, "post",
                        lambda url, **kw: captured.update(url=url, json=kw.get("json")))
    assert notify.send_owner_alert(cfg, "Subj", "Body") is True
    assert captured["url"] == "https://hook.example/x"
    # both Slack ("text") and Discord ("content") fields carry the message
    assert "Subj" in captured["json"]["text"] and "Subj" in captured["json"]["content"]


def test_smtp_used_when_no_webhook(saas_cfg, monkeypatch):
    cfg = dataclasses.replace(saas_cfg, smtp_host="smtp.x", smtp_user="me@x",
                              smtp_password="pw", owner_alert_email="owner@x")
    sent = {}

    from applyfirst.notify import email_smtp

    class FakeNotifier:
        def __init__(self, *a, **k):
            sent["recipient"] = a[5] if len(a) > 5 else k.get("recipient")

        def send(self, subject, body, **k):
            sent["msg"] = (subject, body)

    monkeypatch.setattr(email_smtp, "SmtpNotifier", FakeNotifier)
    assert notify.send_owner_alert(cfg, "Subj", "Body") is True
    assert sent["msg"] == ("Subj", "Body")
    assert sent["recipient"] == "owner@x"


def test_log_only_when_nothing_configured(saas_cfg):
    # saas_cfg has no webhook/SMTP/owner email by default → degrades to a log line.
    assert notify.send_owner_alert(saas_cfg, "Subj", "Body") is False


def test_never_raises_on_transport_error(saas_cfg, monkeypatch):
    cfg = dataclasses.replace(saas_cfg, alert_webhook_url="https://hook")

    import httpx

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "post", boom)
    # webhook fails → falls through to log-only → False, but no exception escapes
    assert notify.send_owner_alert(cfg, "Subj", "Body") is False
