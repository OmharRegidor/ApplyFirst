"""Launch blockers B1 to B5 from docs/OPERATIONS.md section 1, each pinned so it cannot come back.

B1  No AI credential in production must be loud: a CRITICAL log, one owner alert, and /health 503.
    An unfilled placeholder counts as missing, a deliberate AI-off can say so, and a credential
    that is set but failing is caught when every AI call in a cycle falls back.
B2  Structured logging must actually be switched on in every SaaS process (web, worker, backup).
B3  Owner alerts: loud when no channel is set, a test command that names the channel that really
    delivered, a 4xx webhook is not "delivered", the webhook URL never reaches a log, and a blind
    worker turns /health 503. Blind means the site did not answer, not that one term was empty.
B4  A crashed or hung worker is restarted: a real restart loop in entrypoint.sh (run here with the
    worker faked), plus a watchdog inside the worker that ends a cycle that stopped moving. Every
    search attempt is progress, a failed one included, so a slow site is not mistaken for a hang.
B5  Fly has no scheduler, so the worker takes the day's backup itself when the host asks it to,
    and a failed or killed backup never leaves a truncated file or a temp copy behind.

Nothing here sets a real secret, touches the network or sleeps.
"""

from __future__ import annotations

import dataclasses
import gzip
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from applyfirst import backup as core_backup
from applyfirst import log
from applyfirst.saas import app as app_module
from applyfirst.saas import backup, crypto, db, notify, worker
from applyfirst.saas.config import DEADMAN_THRESHOLD, load_saas_config
from applyfirst.tailor import TailoringEngine
from applyfirst.tailor.llm import GeminiProvider
from test_saas_worker import FakeSource, _engine_factory, _raw, _seed

REPO = Path(__file__).resolve().parents[1]
ENTRYPOINT = REPO / "entrypoint.sh"
FLY_TOML = REPO / "fly.toml"
ORACLE = REPO / "deploy" / "oracle"
HOOK = "https://hooks.example/services/T000/B000/s3cr3tt0ken"


def _prod(cfg, **kw):
    """The test config as a production deploy (secure cookies on)."""
    return dataclasses.replace(cfg, secure_cookies=True, **kw)


def _isolated_env(monkeypatch, **env):
    """load_saas_config with no .env file from disk and only the variables given here."""
    monkeypatch.setattr("applyfirst.saas.config.load_dotenv", lambda *a, **k: None)
    for var in ("APPLYFIRST_LOG_JSON", "APPLYFIRST_LOG_LEVEL", "APPLYFIRST_BACKUP_IN_WORKER",
                "APPLYFIRST_WORKER_STALL_SECONDS", "GEMINI_API_KEY", "APPLYFIRST_ALERT_WEBHOOK",
                "APPLYFIRST_AI_OFF_OK", "APPLYFIRST_SMTP_HOST", "APPLYFIRST_SMTP_USER",
                "APPLYFIRST_SMTP_PASSWORD", "APPLYFIRST_OWNER_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("APPLYFIRST_SAAS_SECURE_COOKIES", "0")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return load_saas_config()


def _events(caplog, name, level=None):
    return [r for r in caplog.records
            if r.getMessage() == name and (level is None or r.levelno == level)]


def _critical(caplog, name):
    return _events(caplog, name, logging.CRITICAL)


def _all_log_text(caplog) -> str:
    return "\n".join(f"{r.getMessage()} {getattr(r, 'fields', '')}" for r in caplog.records)


# --- config ------------------------------------------------------------------------------------

def test_structured_logging_is_on_by_default_and_empty_means_default(monkeypatch):
    """The SaaS prints nothing for humans, so its events are its only logs. An empty
    `APPLYFIRST_LOG_JSON=` line falls back to the default like every other setting."""
    assert _isolated_env(monkeypatch).log_json is True
    assert _isolated_env(monkeypatch, APPLYFIRST_LOG_JSON="").log_json is True
    assert _isolated_env(monkeypatch, APPLYFIRST_LOG_JSON="0").log_json is False


def test_new_settings_read_from_the_environment(monkeypatch):
    cfg = _isolated_env(monkeypatch)
    assert cfg.backup_in_worker is False and cfg.worker_stall_seconds == 900
    assert cfg.ai_off_ok is False
    cfg = _isolated_env(monkeypatch, APPLYFIRST_BACKUP_IN_WORKER="1", APPLYFIRST_AI_OFF_OK="1",
                        APPLYFIRST_WORKER_STALL_SECONDS="120", APPLYFIRST_LOG_LEVEL="DEBUG")
    assert cfg.backup_in_worker is True and cfg.worker_stall_seconds == 120
    assert cfg.log_level == "DEBUG" and cfg.ai_off_ok is True


@pytest.mark.parametrize("value", ["<your-gemini-key>", "...", "  ", ""])
def test_an_unfilled_placeholder_counts_as_missing(monkeypatch, value):
    """A copied-but-unfilled sample line must trip the warnings, not silence them."""
    cfg = _isolated_env(monkeypatch, GEMINI_API_KEY=value,
                        APPLYFIRST_ALERT_WEBHOOK="<https://hooks.slack.com/services/...>",
                        APPLYFIRST_SMTP_HOST="smtp.x", APPLYFIRST_SMTP_USER="u",
                        APPLYFIRST_SMTP_PASSWORD="<gmail-app-password>",
                        APPLYFIRST_OWNER_EMAIL="o@x")
    assert cfg.ai_configured is False
    assert cfg.alert_channel is None


def test_a_real_value_is_kept(monkeypatch):
    cfg = _isolated_env(monkeypatch, GEMINI_API_KEY="AIzaRealLookingValue",
                        APPLYFIRST_ALERT_WEBHOOK=HOOK)
    assert cfg.ai_configured is True and cfg.alert_channel == "webhook"


def test_alert_channel_matches_what_notify_would_use(saas_cfg):
    assert saas_cfg.alert_channel is None
    smtp = dataclasses.replace(saas_cfg, smtp_host="h", smtp_user="u", smtp_password="p",
                               owner_alert_email="o@x")
    assert smtp.alert_channel == "smtp"
    assert dataclasses.replace(smtp, owner_alert_email=None).alert_channel is None
    assert dataclasses.replace(smtp, alert_webhook_url="https://hook").alert_channel == "webhook"


# --- B2: every SaaS process switches logging on -------------------------------------------------

class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *a, **k):
        self.calls.append((a, k))


def test_the_web_entry_switches_logging_on(monkeypatch, saas_cfg):
    rec = _Recorder()
    monkeypatch.setattr(log, "configure", rec)
    monkeypatch.setattr(app_module, "load_saas_config", lambda: saas_cfg)
    app_module.__getattr__("app")
    assert rec.calls == [((saas_cfg.log_json, saas_cfg.log_level), {})]


def test_create_app_alone_leaves_logging_to_the_caller(monkeypatch, saas_cfg):
    """Tests build apps through create_app. Configuring there would set propagate=False on the
    package logger and blind every caplog-based test that runs after it."""
    rec = _Recorder()
    monkeypatch.setattr(log, "configure", rec)
    app_module.create_app(saas_cfg)
    assert rec.calls == []


def test_the_worker_switches_logging_on_before_anything_can_fail(monkeypatch, saas_cfg):
    order = []
    monkeypatch.setattr(log, "configure", lambda *a, **k: order.append("configure"))
    monkeypatch.setattr(worker, "load_saas_config", lambda: saas_cfg)
    monkeypatch.setattr(notify, "send_owner_alert", lambda *a: True)

    def no_master(*a, **k):
        order.append("master")
        raise crypto.CryptoError("none")

    monkeypatch.setattr(crypto, "load_master_key", no_master)
    assert worker.main(["--once"]) == 1
    assert order == ["configure", "master"], "worker_no_master_key would be logged into the void"


def test_the_backup_command_switches_logging_on(monkeypatch, saas_cfg):
    order = []
    monkeypatch.setattr(log, "configure", lambda *a, **k: order.append("configure"))
    monkeypatch.setattr(backup, "load_saas_config", lambda: saas_cfg)
    monkeypatch.setattr(backup, "run_backup", lambda cfg: order.append("backup") or "x")
    assert backup.main() == 0
    assert order == ["configure", "backup"]


# --- B1 and B3: loud when production is missing something ----------------------------------------

def test_production_without_ai_is_loud_and_alerts_the_owner_once(saas_cfg, monkeypatch, caplog):
    sent = []
    monkeypatch.setattr(notify, "send_owner_alert", lambda cfg, s, b: sent.append(s) or True)
    cfg = _prod(saas_cfg, alert_webhook_url="https://hook")
    conn = db.init_db(cfg.db_path)
    with caplog.at_level(logging.INFO, logger="applyfirst.saas.worker"):
        worker._startup_checks(conn, cfg)
        worker._startup_checks(conn, cfg)          # a restart inside the cooldown
    assert len(_critical(caplog, "ai_not_configured")) == 2, "every start says it"
    assert len(sent) == 1 and "without AI" in sent[0], "but the owner is paged once"
    assert _critical(caplog, "owner_alerts_not_configured") == []
    assert db.get_worker_meta(conn, "ai_state") == "off"
    conn.close()


def test_ai_off_on_purpose_is_quiet(saas_cfg, monkeypatch, caplog):
    sent = []
    monkeypatch.setattr(notify, "send_owner_alert", lambda *a: sent.append(a) or True)
    cfg = _prod(saas_cfg, alert_webhook_url="https://hook", ai_off_ok=True)
    conn = db.init_db(cfg.db_path)
    with caplog.at_level(logging.INFO, logger="applyfirst.saas.worker"):
        worker._startup_checks(conn, cfg)
    assert _critical(caplog, "ai_not_configured") == [] and sent == []
    assert _events(caplog, "ai_off_by_choice", logging.WARNING)
    assert db.get_worker_meta(conn, "ai_state") == "off_ok"
    conn.close()


def test_production_without_an_alert_channel_is_loud(saas_cfg, caplog):
    cfg = _prod(saas_cfg, gemini_api_key="g")
    conn = db.init_db(cfg.db_path)
    with caplog.at_level(logging.INFO, logger="applyfirst.saas.worker"):
        worker._startup_checks(conn, cfg)
    assert len(_critical(caplog, "owner_alerts_not_configured")) == 1
    assert _critical(caplog, "ai_not_configured") == []
    assert db.get_worker_meta(conn, "ai_state") == "on"
    conn.close()


def test_a_development_box_is_left_alone(saas_cfg, monkeypatch, caplog):
    sent = []
    monkeypatch.setattr(notify, "send_owner_alert", lambda *a: sent.append(a) or True)
    conn = db.init_db(saas_cfg.db_path)
    with caplog.at_level(logging.INFO, logger="applyfirst.saas.worker"):
        worker._startup_checks(conn, saas_cfg)
    assert [r.getMessage() for r in caplog.records] == ["worker_started"]
    assert sent == []
    conn.close()


def test_a_worker_that_cannot_start_tells_the_owner_once(saas_cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(log, "configure", lambda *a, **k: None)
    monkeypatch.setattr(worker, "load_saas_config", lambda: saas_cfg)
    monkeypatch.setattr(notify, "send_owner_alert", lambda cfg, s, b: sent.append((s, b)) or True)

    def no_master(*a, **k):
        raise crypto.CryptoError("no master key configured")

    monkeypatch.setattr(crypto, "load_master_key", no_master)
    assert worker.main([]) == 1 and worker.main([]) == 1      # two restarts of the loop
    assert len(sent) == 1 and sent[0][0] == "Agad worker cannot start"
    assert "no master key configured" in sent[0][1]


# --- /health -----------------------------------------------------------------------------------

def _health(cfg, *, blind="0", ai_state=None, last=True, started_ago=0.0):
    conn = db.init_db(cfg.db_path)
    if last:
        db.set_worker_meta(conn, "last_cycle_at", db._now_iso())
    db.set_worker_meta(conn, "blind_cycles", str(blind))
    if ai_state is not None:
        db.set_worker_meta(conn, "ai_state", ai_state)
    conn.close()
    app = app_module.create_app(cfg)
    app.state.started_at = time.monotonic() - started_ago
    return TestClient(app).get("/health")


def test_health_pages_when_production_has_no_ai(saas_cfg):
    r = _health(_prod(saas_cfg))
    assert r.status_code == 503 and r.json()["ai"] == "off" and r.json()["status"] == "degraded"
    assert _health(_prod(saas_cfg, gemini_api_key="g")).status_code == 200
    assert _health(_prod(saas_cfg, ai_off_ok=True)).status_code == 200, "off on purpose"
    assert _health(saas_cfg).status_code == 200, "a dev box without AI is fine"


def test_health_believes_the_worker_about_the_ai(saas_cfg):
    """The worker writes the letters, and on Oracle the web and the worker restart separately."""
    assert _health(_prod(saas_cfg), ai_state="on").status_code == 200
    r = _health(_prod(saas_cfg, gemini_api_key="g"), ai_state="off")
    assert r.status_code == 503 and r.json()["ai"] == "off"
    assert _health(_prod(saas_cfg), ai_state="off_ok").status_code == 200


def test_health_pages_when_the_worker_is_blind(saas_cfg):
    assert _health(saas_cfg, blind=DEADMAN_THRESHOLD - 1).status_code == 200
    r = _health(saas_cfg, blind=DEADMAN_THRESHOLD)
    assert r.status_code == 503 and r.json()["polling"] == "blind"


def test_a_corrupted_blind_counter_degrades_instead_of_crashing(saas_cfg):
    r = _health(saas_cfg, blind="garbage")
    assert r.status_code == 503 and r.json()["polling"] == "blind"


def test_a_worker_that_never_finishes_a_cycle_pages_after_the_grace_window(saas_cfg):
    grace = saas_cfg.worker_interval * app_module._HEALTH_STALE_FACTOR
    r = _health(saas_cfg, last=False, started_ago=grace - 60)
    assert r.status_code == 200 and r.json()["worker"] == "starting"
    r = _health(saas_cfg, last=False, started_ago=grace + 60)
    assert r.status_code == 503 and r.json()["worker"] == "never_ran"


def test_the_worker_and_health_trip_on_the_same_cycle(saas_cfg, monkeypatch):
    """The cycle that makes the worker page the owner is the cycle /health turns 503, no sooner."""
    monkeypatch.setattr(notify, "send_owner_alert", lambda *a: True)
    conn = db.init_db(saas_cfg.db_path)
    client = TestClient(app_module.create_app(saas_cfg))
    blind = worker.CycleResult(keywords=1, jobs_seen=0, site_ok=False)
    for n in range(1, DEADMAN_THRESHOLD + 1):
        worker._record_heartbeat(conn, blind, saas_cfg)
        paged = db.get_worker_meta(conn, "last_owner_alert_at") is not None
        assert paged is (n >= DEADMAN_THRESHOLD)
        assert (client.get("/health").status_code == 503) is (n >= DEADMAN_THRESHOLD)
    conn.close()


# --- B3: the alert channel ---------------------------------------------------------------------

def test_a_webhook_that_answers_an_error_is_not_delivered_and_its_url_stays_out_of_logs(
        saas_cfg, monkeypatch, caplog):
    cfg = dataclasses.replace(saas_cfg, alert_webhook_url=HOOK)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(
        404, request=httpx.Request("POST", url)))
    with caplog.at_level(logging.ERROR, logger="applyfirst.saas.notify"):
        assert notify.send_owner_alert(cfg, "s", "b") is False
    assert _events(caplog, "owner_alert_webhook_failed")
    assert "s3cr3tt0ken" not in _all_log_text(caplog), "the webhook URL works like a password"


def test_a_webhook_that_cannot_connect_keeps_its_url_out_of_logs(saas_cfg, monkeypatch, caplog):
    cfg = dataclasses.replace(saas_cfg, alert_webhook_url=HOOK)

    def refuse(url, **kw):
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(httpx, "post", refuse)
    with caplog.at_level(logging.ERROR, logger="applyfirst.saas.notify"):
        assert notify.send_owner_alert(cfg, "s", "b") is False
    assert "s3cr3tt0ken" not in _all_log_text(caplog)


def _patch_channels(monkeypatch, *, webhook_status=200, smtp_ok=True):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(
        webhook_status, request=httpx.Request("POST", url)))
    from applyfirst.notify import email_smtp

    class FakeSmtp:
        def __init__(self, *a, **k):
            pass

        def send(self, *a, **k):
            if not smtp_ok:
                raise OSError("smtp down")

    monkeypatch.setattr(email_smtp, "SmtpNotifier", FakeSmtp)


def _test_command(monkeypatch, cfg):
    monkeypatch.setattr(log, "configure", lambda *a, **k: None)
    monkeypatch.setattr("applyfirst.saas.config.load_saas_config", lambda: cfg)
    return notify.main(["--test"])


def test_the_alert_test_command_passes_when_the_configured_channel_delivers(
        saas_cfg, monkeypatch, capsys):
    _patch_channels(monkeypatch)
    assert _test_command(monkeypatch, dataclasses.replace(saas_cfg, alert_webhook_url=HOOK)) == 0
    assert "configured: webhook, delivered by: webhook" in capsys.readouterr().out


def test_the_alert_test_command_fails_when_the_webhook_is_broken_even_if_smtp_steps_in(
        saas_cfg, monkeypatch, capsys):
    _patch_channels(monkeypatch, webhook_status=404)
    cfg = dataclasses.replace(saas_cfg, alert_webhook_url=HOOK, smtp_host="h", smtp_user="u",
                              smtp_password="p", owner_alert_email="o@x")
    assert _test_command(monkeypatch, cfg) == 1
    out = capsys.readouterr().out
    assert "configured: webhook, delivered by: smtp" in out and "webhook failed" in out


def test_the_alert_test_command_fails_with_nothing_set_up(saas_cfg, monkeypatch, capsys):
    assert _test_command(monkeypatch, saas_cfg) == 1
    assert "configured: none, delivered by: nothing" in capsys.readouterr().out
    assert notify.main([]) == 2


# --- B3: blind means the site did not answer ----------------------------------------------------

class _TermSource(FakeSource):
    """Returns jobs only for the terms given; the rest come back empty. Can fail every search."""

    def __init__(self, jobs_for=(), fail=False):
        super().__init__([_raw("c1")])
        self.jobs_for, self.fail, self.searched = set(jobs_for), fail, []

    def search_latest(self, keyword):
        self.searched.append(keyword)
        if self.fail:
            raise httpx.ReadTimeout("site not answering")
        return list(self._jobs) if keyword in self.jobs_for else []


def test_one_empty_term_is_not_blind_when_the_site_answers(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key, keyword="claude code")                  # a term with no posts
    src = _TermSource(jobs_for={worker._CANARY_TERM})
    for _ in range(DEADMAN_THRESHOLD + 1):
        r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                            sender=lambda *a, **k: "m", polite=False)
        worker._record_heartbeat(conn, r)
    assert r.site_ok is True and src.searched[-1] == worker._CANARY_TERM
    assert db.get_worker_meta(conn, "blind_cycles") == "0"
    conn.close()


def test_the_site_not_answering_is_blind(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key, keyword="claude code")
    for _ in range(DEADMAN_THRESHOLD):
        r = worker.run_once(conn, _TermSource(), saas_cfg, master_key,
                            engine_factory=_engine_factory, sender=lambda *a, **k: "m",
                            polite=False)
        worker._record_heartbeat(conn, r)
    assert r.site_ok is False
    assert db.get_worker_meta(conn, "blind_cycles") == str(DEADMAN_THRESHOLD)
    conn.close()


def test_no_canary_search_when_some_term_returned_jobs(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key, keyword="data entry")
    src = _TermSource(jobs_for={"data entry"})
    r = worker.run_once(conn, src, saas_cfg, master_key, engine_factory=_engine_factory,
                        sender=lambda *a, **k: "m", polite=False)
    assert r.site_ok is None and worker._CANARY_TERM not in src.searched
    conn.close()


# --- B1: a credential that is set but failing ----------------------------------------------------

class _FailingProvider:
    name = "gemini"

    def generate(self, system, user):
        req = httpx.Request("POST", "https://generativelanguage.example/v1?key=LEAKME")
        httpx.Response(403, request=req).raise_for_status()   # the real error, URL in its text


class _FlakyProvider:
    """Fails both attempts at the first letter (the engine retries once), then answers."""
    name = "gemini"

    def __init__(self):
        self.calls = 0

    def generate(self, system, user):
        self.calls += 1
        if self.calls <= 2:
            _FailingProvider().generate(system, user)
        return ('{"digest": "d", "application_subject": "s", "screening_questions": [], '
                '"compliance_token": null, "cover_letter": "Hello.", '
                '"resume_overrides": {"emphasize_skills": []}}')


def _ai_cycles(saas_cfg, master_key, monkeypatch, sent, provider, cycles, *, cfg=None):
    """A baseline, then ``cycles`` polls that each bring one new job to tailor."""
    monkeypatch.setattr(notify, "send_owner_alert", lambda c, s, b: sent.append(s) or True)
    cfg = cfg or dataclasses.replace(saas_cfg, gemini_api_key="set-but-wrong")
    conn = db.init_db(cfg.db_path)
    _seed(conn, master_key)
    kw = dict(engine_factory=lambda: TailoringEngine(provider=provider),
              sender=lambda *a, **k: "m", polite=False)
    worker.run_once(conn, FakeSource([_raw("0")]), cfg, master_key, **kw)       # baseline
    results = [worker.run_once(conn, FakeSource([_raw(str(n))]), cfg, master_key, **kw)
               for n in range(1, cycles + 1)]
    return conn, results


def _second_poll_with_failing_ai(saas_cfg, master_key, monkeypatch, sent):
    conn, results = _ai_cycles(saas_cfg, master_key, monkeypatch, sent, _FailingProvider(), 1)
    return conn, results[-1]


def test_one_failed_ai_cycle_is_logged_but_does_not_page(saas_cfg, master_key, monkeypatch,
                                                         caplog):
    """A single unlucky cycle can be a passing Gemini overload."""
    sent = []
    with caplog.at_level(logging.WARNING):
        conn, r = _second_poll_with_failing_ai(saas_cfg, master_key, monkeypatch, sent)
    assert r.ai_calls == 1 and r.ai_fallbacks == 1
    assert _events(caplog, "ai_all_failed", logging.ERROR)
    assert sent == [] and db.get_worker_meta(conn, "ai_failed_cycles") == "1"
    conn.close()


def test_a_failing_ai_streak_pages_the_owner_once(saas_cfg, master_key, monkeypatch):
    sent = []
    conn, _ = _ai_cycles(saas_cfg, master_key, monkeypatch, sent, _FailingProvider(),
                         worker._AI_FAIL_STREAK + 2)
    assert sent == ["Agad's AI calls are failing"], "paged at the streak, then debounced"
    conn.close()


def test_a_working_ai_call_resets_the_streak(saas_cfg, master_key, monkeypatch, caplog):
    sent = []
    with caplog.at_level(logging.ERROR, logger="applyfirst.saas.worker"):
        conn, results = _ai_cycles(saas_cfg, master_key, monkeypatch, sent, _FlakyProvider(), 3)
    assert results[0].ai_fallbacks == 1 and results[1].ai_fallbacks == 0
    assert db.get_worker_meta(conn, "ai_failed_cycles") == "0" and sent == []
    conn.close()


def test_no_ai_credential_means_nothing_to_count(saas_cfg, master_key, monkeypatch, caplog):
    sent = []
    with caplog.at_level(logging.ERROR, logger="applyfirst.saas.worker"):
        conn, results = _ai_cycles(saas_cfg, master_key, monkeypatch, sent, None, 3, cfg=saas_cfg)
    assert all(r.ai_calls == 0 for r in results)
    assert _events(caplog, "ai_all_failed") == [] and sent == []
    conn.close()


def test_a_failed_ai_call_logs_its_status_and_never_its_url(saas_cfg, master_key, monkeypatch,
                                                            caplog):
    with caplog.at_level(logging.WARNING):
        conn, _ = _second_poll_with_failing_ai(saas_cfg, master_key, monkeypatch, [])
    with pytest.raises(httpx.HTTPStatusError, match="LEAKME"):   # so the check below can fail
        _FailingProvider().generate("s", "u")
    failed = _events(caplog, "ai_call_failed", logging.WARNING)
    assert failed and failed[0].fields["status"] == 403
    assert failed[0].fields["error"] == "HTTPStatusError"
    assert "LEAKME" not in _all_log_text(caplog)
    conn.close()


def test_the_gemini_credential_rides_in_a_header_never_the_url():
    seen = {}

    def handler(request):
        seen["url"], seen["headers"] = str(request.url), request.headers
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    p = GeminiProvider("the-credential", "m")
    p._client = httpx.Client(transport=httpx.MockTransport(handler))
    p.generate("s", "u")
    assert "the-credential" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "the-credential"


# --- B4: the watchdog inside the worker ----------------------------------------------------------

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _dog(limit=60):
    clock, exits = _Clock(), []
    return worker._Watchdog(limit, clock=clock, exit_fn=exits.append), clock, exits


def test_the_watchdog_ends_a_cycle_that_stopped_moving(caplog):
    dog, clock, exits = _dog()
    dog.arm()
    clock.t += 61
    with caplog.at_level(logging.CRITICAL, logger="applyfirst.saas.worker"):
        assert dog.check() is True
    assert exits == [worker._STALL_EXIT_CODE]
    assert _critical(caplog, "worker_stalled")


def test_the_watchdog_leaves_a_long_cycle_alone_while_it_moves():
    dog, clock, exits = _dog()
    dog.arm()
    for _ in range(10):                  # ten minutes of work, a beat every 50s
        clock.t += 50
        dog.beat()
        assert dog.check() is False
    assert exits == []


def test_the_watchdog_ignores_the_sleep_between_cycles():
    dog, clock, exits = _dog()
    dog.arm()
    dog.disarm()
    clock.t += 10_000
    assert dog.check() is False and exits == []
    dog.arm()                            # a new cycle starts the count from now, not from before
    assert dog.check() is False and exits == []


def test_the_real_watchdog_thread_fires_on_a_stall_and_not_before():
    clock, codes, fired = _Clock(), [], threading.Event()
    dog = worker._Watchdog(60, clock=clock, exit_fn=lambda c: (codes.append(c), fired.set()))
    dog.start(every=0.01)
    clock.t += 1000                      # disarmed: the sleep between cycles never counts
    assert not fired.wait(0.1)
    dog.arm()
    assert not fired.wait(0.1)
    clock.t += 61
    assert fired.wait(2) and codes[0] == worker._STALL_EXIT_CODE


def test_a_cycle_beats_for_every_term_job_and_alert(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    _seed(conn, master_key)
    beats = []
    kw = dict(engine_factory=_engine_factory, sender=lambda *a, **k: "m", polite=False,
              beat=lambda: beats.append(1))
    worker.run_once(conn, FakeSource([_raw("1")]), saas_cfg, master_key, **kw)   # baseline
    assert len(beats) == 1 + 1                                       # one job + the term
    beats.clear()
    r = worker.run_once(conn, FakeSource([_raw("1"), _raw("2")]), saas_cfg, master_key, **kw)
    handled = r.sent + r.failed + r.capped + r.skipped
    assert handled >= 1 and len(beats) == 2 + 1 + handled            # jobs + term + each alert
    conn.close()


def test_a_failed_search_still_beats(saas_cfg, master_key):
    """A site that times out on every term must read as blind, never as a hung worker."""
    conn = db.init_db(saas_cfg.db_path)
    for i, term in enumerate(("a", "b", "c")):
        _seed(conn, master_key, sub=f"s{i}", email=f"{i}@x.com", keyword=term)
    beats = []
    worker.run_once(conn, _TermSource(fail=True), saas_cfg, master_key,
                    engine_factory=_engine_factory, sender=lambda *a, **k: "m", polite=False,
                    beat=lambda: beats.append(1))
    assert len(beats) == 3 + 1, "one per failed term, plus the canary check"
    conn.close()


def test_a_cycle_disarms_the_watchdog_even_when_it_crashes(saas_cfg, master_key, monkeypatch):
    dog, _, _ = _dog()

    def boom(*a, **k):
        raise RuntimeError("cycle died")

    monkeypatch.setattr(worker, "run_once", boom)
    conn = db.init_db(saas_cfg.db_path)
    with pytest.raises(RuntimeError):
        worker._cycle(conn, None, saas_cfg, master_key, dog)
    assert dog._armed is False, "an armed dog would kill the worker during its sleep"
    conn.close()


def test_the_daemon_loop_starts_the_watchdog_and_hands_it_to_every_cycle(saas_cfg, master_key,
                                                                          monkeypatch):
    cfg = dataclasses.replace(saas_cfg, worker_stall_seconds=123)
    monkeypatch.setattr(log, "configure", lambda *a, **k: None)
    monkeypatch.setattr(worker, "load_saas_config", lambda: cfg)
    monkeypatch.setattr(crypto, "load_master_key", lambda: master_key)
    monkeypatch.setattr("applyfirst.sources.base.make_client", lambda *a, **k: None)
    monkeypatch.setattr("applyfirst.sources.onlinejobsph.OnlineJobsPHSource", lambda client: None)
    monkeypatch.setattr(worker, "_startup_checks", lambda conn, cfg: None)
    made = []

    class FakeDog:
        def __init__(self, limit):
            self.limit, self.started = limit, False
            made.append(self)

        def start(self):
            self.started = True

    handed = []

    class Stop(Exception):
        pass

    def stop_sleeping(_):
        raise Stop

    monkeypatch.setattr(worker, "_Watchdog", FakeDog)
    monkeypatch.setattr(worker, "_cycle", lambda conn, src, c, mk, dog=None: handed.append(dog))
    monkeypatch.setattr(worker.time, "sleep", stop_sleeping)
    with pytest.raises(Stop):
        worker.main([])
    assert len(made) == 1 and made[0].limit == 123 and made[0].started
    assert handed == [made[0]]


# --- B4: the restart loop in entrypoint.sh -------------------------------------------------------

def _loop_body() -> str:
    m = re.search(r"^\(\n(.*?)^\) &$", ENTRYPOINT.read_text(encoding="utf-8"), re.S | re.M)
    assert m, "the worker supervisor must be a backgrounded ( ... ) & block"
    return m.group(1)


def test_the_dead_watchdog_is_gone_and_a_restart_loop_runs_the_worker():
    src = ENTRYPOINT.read_text(encoding="utf-8")
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    assert 'wait "$worker_pid"' not in code and "kill 1" not in code
    body = _loop_body()
    assert "while :; do" in body and "python -m applyfirst.saas.worker" in body
    last = [line for line in code.splitlines() if line.strip()][-1]
    assert last.startswith("exec uvicorn applyfirst.saas.app:app"), "uvicorn must stay the foreground"
    assert code.index(") &") < code.index("exec uvicorn"), "the loop must start before uvicorn"


_SH = shutil.which("sh")


@pytest.mark.skipif(_SH is None, reason="needs a POSIX sh (Git Bash on Windows, any Linux)")
def test_the_restart_loop_really_restarts_and_backs_off(tmp_path):
    """Run the real loop body from entrypoint.sh with the worker, sleep and date faked: seven fast
    crashes (enough to reach the 5 minute cap), one healthy 15-minute run, two more crashes."""
    harness = tmp_path / "sim.sh"
    harness.write_text(
        "set -eu\n"
        'echo 0 > "$CLOCK"\n'
        'echo 0 > "$RUNS"\n'
        'LENGTHS="1 1 1 1 1 1 1 900 1 1"\n'
        'date() { cat "$CLOCK"; }\n'
        'sleep() { echo "SLEEP $1"; echo $(( $(cat "$CLOCK") + $1 )) > "$CLOCK"; }\n'
        'python() {\n'
        '  n=$(( $(cat "$RUNS") + 1 )); echo "$n" > "$RUNS"\n'
        '  len=$(echo $LENGTHS | cut -d" " -f"$n")\n'
        '  if [ -z "$len" ]; then exit 0; fi\n'
        '  echo $(( $(cat "$CLOCK") + len )) > "$CLOCK"\n'
        '  return 3\n'
        '}\n' + _loop_body(), encoding="utf-8", newline="\n")
    env = {**os.environ, "CLOCK": f"{tmp_path.as_posix()}/clock", "RUNS": f"{tmp_path.as_posix()}/runs"}
    out = subprocess.run([_SH, str(harness)], capture_output=True, text=True, timeout=60, env=env)
    sleeps = [int(s) for s in re.findall(r"^SLEEP (\d+)$", out.stdout, re.M)]
    assert sleeps == [10, 20, 40, 80, 160, 300, 300, 10, 10, 20], out.stdout + out.stderr
    assert out.stderr.count("worker exited with status 3") == 10


@pytest.mark.skipif(_SH is None, reason="needs a POSIX sh")
def test_entrypoint_parses():
    assert subprocess.run([_SH, "-n", str(ENTRYPOINT)], capture_output=True).returncode == 0


# --- B5: the worker takes the day's backup when the host asks ------------------------------------

def test_no_backup_unless_the_host_asks(saas_cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "run_backup", lambda cfg: calls.append(1))
    conn = db.init_db(saas_cfg.db_path)
    assert worker._maybe_backup(conn, saas_cfg, today="2026-09-23") is False
    assert calls == []
    conn.close()


def test_one_backup_a_day(saas_cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "run_backup", lambda cfg: calls.append(cfg.backup_dir) or "x")
    cfg = dataclasses.replace(saas_cfg, backup_in_worker=True)
    conn = db.init_db(cfg.db_path)
    assert worker._maybe_backup(conn, cfg, today="2026-09-23") is True
    assert worker._maybe_backup(conn, cfg, today="2026-09-23") is False
    assert worker._maybe_backup(conn, cfg, today="2026-09-24") is True
    assert len(calls) == 2
    conn.close()


def test_a_failed_backup_is_retried_and_pages_the_owner_once(saas_cfg, monkeypatch, caplog):
    sent = []
    monkeypatch.setattr(notify, "send_owner_alert", lambda cfg, s, b: sent.append(s) or True)

    def full_disk(cfg):
        raise OSError("No space left on device")

    monkeypatch.setattr(backup, "run_backup", full_disk)
    cfg = dataclasses.replace(saas_cfg, backup_in_worker=True)
    conn = db.init_db(cfg.db_path)
    with caplog.at_level(logging.ERROR, logger="applyfirst.saas.worker"):
        assert worker._maybe_backup(conn, cfg, today="2026-09-23") is False
        assert worker._maybe_backup(conn, cfg, today="2026-09-23") is False
    assert db.get_worker_meta(conn, "last_backup_date") is None, "a failure must not be stamped"
    assert sum(r.getMessage() == "backup_failed" for r in caplog.records) == 2
    assert sent == ["Agad backup failed"], "paged once, not every cycle"
    conn.close()


def test_an_alert_that_did_not_get_through_is_retried_soon(saas_cfg, monkeypatch):
    results = iter([False, True])
    sent = []
    monkeypatch.setattr(notify, "send_owner_alert", lambda c, s, b: sent.append(s) or next(results))
    cfg = dataclasses.replace(saas_cfg, alert_webhook_url=HOOK)
    conn = db.init_db(cfg.db_path)
    assert worker._alert_owner_once(conn, cfg, "k", "subject", "body") is False
    stamp = float(db.get_worker_meta(conn, "k"))
    waits = worker._OWNER_ALERT_COOLDOWN - (time.time() - stamp)
    assert abs(waits - worker._ALERT_RETRY) < 5, "retry in 15 minutes, not 6 hours"
    db.set_worker_meta(conn, "k", str(stamp - worker._ALERT_RETRY - 1))       # 15 minutes later
    assert worker._alert_owner_once(conn, cfg, "k", "subject", "body") is True
    assert worker._alert_owner_once(conn, cfg, "k", "subject", "body") is False  # now debounced
    assert len(sent) == 2
    conn.close()


def test_with_no_channel_the_log_line_is_not_repeated_every_cycle(saas_cfg, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_owner_alert", lambda c, s, b: sent.append(s) or False)
    conn = db.init_db(saas_cfg.db_path)
    worker._alert_owner_once(conn, saas_cfg, "k", "subject", "body")
    stamp = float(db.get_worker_meta(conn, "k"))
    db.set_worker_meta(conn, "k", str(stamp - worker._ALERT_RETRY - 1))       # 15 minutes later
    worker._alert_owner_once(conn, saas_cfg, "k", "subject", "body")
    assert len(sent) == 1, "with nothing set up, retrying would only repeat the same log line"
    conn.close()


def test_a_backup_runs_inside_the_watched_cycle(saas_cfg, master_key, monkeypatch):
    order = []
    monkeypatch.setattr(worker, "run_once", lambda *a, **k: order.append("cycle") or worker.CycleResult())
    monkeypatch.setattr(worker, "_maybe_backup", lambda conn, cfg: order.append("backup"))
    dog, _, _ = _dog()
    monkeypatch.setattr(dog, "disarm", lambda: order.append("disarm"))
    conn = db.init_db(saas_cfg.db_path)
    worker._cycle(conn, None, saas_cfg, master_key, dog)
    assert order == ["cycle", "backup", "disarm"], "a hung backup must be caught by the watchdog"
    conn.close()


def test_the_oracle_backup_command_reports_a_failure(saas_cfg, monkeypatch, caplog):
    """The Oracle timer runs this, not the worker, so it must log and page on its own."""
    sent = []
    monkeypatch.setattr(log, "configure", lambda *a, **k: None)
    monkeypatch.setattr(backup, "load_saas_config", lambda: saas_cfg)
    monkeypatch.setattr(notify, "send_owner_alert", lambda cfg, s, b: sent.append(s) or True)

    def full_disk(cfg):
        raise OSError("No space left on device")

    monkeypatch.setattr(backup, "run_backup", full_disk)
    with caplog.at_level(logging.ERROR, logger="applyfirst.saas.backup"):
        assert backup.main() == 1
    assert _events(caplog, "backup_failed", logging.ERROR) and sent == ["Agad backup failed"]


# --- B5: a backup never leaves a broken or oversized file behind ---------------------------------

def _live_db(tmp_path) -> Path:
    path = tmp_path / "live.db"
    db.init_db(str(path)).close()
    return path


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_a_backup_that_dies_mid_gzip_leaves_nothing_behind(tmp_path, monkeypatch):
    src, out_dir = _live_db(tmp_path), tmp_path / "backups"

    class Boom(gzip.GzipFile):
        def write(self, data):
            raise OSError("No space left on device")

    monkeypatch.setattr(core_backup.gzip, "open", lambda path, mode: Boom(path, mode))
    with pytest.raises(OSError):
        core_backup.backup_db(src, out_dir, keep=7, stamp="20260923-000000")
    assert _names(out_dir) == [], "no truncated .db.gz and no temporary copy may survive"


def _junk(folder: Path, name: str, *, age: float) -> Path:
    path = folder / name
    path.write_bytes(b"x" * 1000)
    then = time.time() - age
    os.utime(path, (then, then))
    return path


def test_leftovers_from_a_killed_backup_are_swept(tmp_path):
    src, out_dir = _live_db(tmp_path), tmp_path / "backups"
    out_dir.mkdir()
    for junk in (".live-20260922-000000.tmp.db", ".live-20260922-000000.tmp.db-journal",
                 ".live-20260922-000000.db.gz.part"):
        _junk(out_dir, junk, age=2 * core_backup._SWEEP_AGE)
    made = core_backup.backup_db(src, out_dir, keep=7, stamp="20260923-000000")
    assert _names(out_dir) == [made.name] == ["live-20260923-000000.db.gz"]
    with gzip.open(made) as f:
        assert f.read(16).startswith(b"SQLite format 3")


def test_the_sweep_spares_a_backup_that_may_still_be_running(tmp_path):
    src, out_dir = _live_db(tmp_path), tmp_path / "backups"
    out_dir.mkdir()
    fresh = _junk(out_dir, ".live-20260923-000500.tmp.db", age=10)
    core_backup.backup_db(src, out_dir, keep=7, stamp="20260923-000000")
    assert fresh.exists(), "a second backup running right now must keep its files"


def test_a_failed_backup_removes_its_own_journal_files(tmp_path, monkeypatch):
    src, out_dir = _live_db(tmp_path), tmp_path / "backups"
    out_dir.mkdir()
    for suffix in ("-journal", "-wal", "-shm"):     # as a copy that died inside SQLite leaves them
        _junk(out_dir, f".live-20260923-000000.tmp.db{suffix}", age=10)
    monkeypatch.setattr(core_backup.gzip, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError):
        core_backup.backup_db(src, out_dir, keep=7, stamp="20260923-000000")
    assert _names(out_dir) == []


def test_two_apps_backing_up_into_one_folder_never_touch_each_other(tmp_path):
    """On the Oracle VM the V1 CLI (applyfirst.db) and the SaaS (applyfirst-saas.db) share
    backups/. A loose "applyfirst-*" pattern made V1 delete its own fresh backup, and the SaaS
    temp files, once the SaaS had filled its seven slots."""
    folder = tmp_path / "backups"
    v1, saas = tmp_path / "applyfirst.db", tmp_path / "applyfirst-saas.db"
    db.init_db(str(v1)).close()
    db.init_db(str(saas)).close()
    for day in range(1, 8):
        core_backup.backup_db(saas, folder, keep=7, stamp=f"2026092{day}-030000")
    saas_temp = _junk(folder, ".applyfirst-saas-20260920-030000.tmp.db", age=2 * core_backup._SWEEP_AGE)
    made = core_backup.backup_db(v1, folder, keep=7, stamp="20260928-000100")
    assert made.exists(), "V1 must keep the backup it just wrote"
    assert len([n for n in _names(folder) if n.startswith("applyfirst-saas-")]) == 7
    assert saas_temp.exists(), "V1's sweep must leave the SaaS temp files alone"


def test_a_backup_refuses_to_fill_the_disk(tmp_path, monkeypatch):
    src, out_dir = _live_db(tmp_path), tmp_path / "backups"
    monkeypatch.setattr(core_backup.shutil, "disk_usage",
                        lambda p: shutil._ntuple_diskusage(10**9, 10**9, 10))
    with pytest.raises(OSError, match="not enough free disk"):
        core_backup.backup_db(src, out_dir, keep=7)
    assert _names(out_dir) == []


# --- the deploy files carry all of it -----------------------------------------------------------

def test_fly_turns_on_logging_and_the_daily_backup():
    tomllib = pytest.importorskip("tomllib")
    env = tomllib.loads(FLY_TOML.read_text(encoding="utf-8"))["env"]
    assert env.get("APPLYFIRST_LOG_JSON") == "1"
    assert env.get("APPLYFIRST_BACKUP_IN_WORKER") == "1"
    assert env.get("APPLYFIRST_BACKUP_DIR", "").startswith("/data/"), "backups must be on the volume"


def test_fly_names_every_secret_and_commits_none():
    tomllib = pytest.importorskip("tomllib")
    text = FLY_TOML.read_text(encoding="utf-8")
    env = tomllib.loads(text)["env"]
    for secret in ("SESSION_SECRET", "APPLYFIRST_MASTER_KEY", "GOOGLE_CLIENT_ID",
                   "GOOGLE_CLIENT_SECRET", "GEMINI_API_KEY", "APPLYFIRST_ALERT_WEBHOOK"):
        assert re.search(rf"^#\s+{secret}\b", text, re.M), f"fly.toml does not list {secret}"
        assert secret not in env, f"{secret} is a secret and must never be in [env]"


def test_oracle_marks_the_ai_credential_required_without_clobbering_the_shared_one():
    """GEMINI_API_KEY is shared with the V1 CLI in the same .env, and the last line wins. An
    uncommented placeholder appended from the sample would replace the real key for both apps."""
    sample = (ORACLE / "saas-env.sample").read_text(encoding="utf-8")
    assert re.search(r"^#\s*GEMINI_API_KEY=.*\[REQUIRED\]", sample, re.M)
    assert not re.search(r"^GEMINI_API_KEY=", sample, re.M), "never ship it uncommented"
    assert "SHARED" in sample


def test_the_oracle_readme_block_does_not_clobber_or_fake_a_channel():
    readme = (ORACLE / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"^GEMINI_API_KEY=", readme, re.M), "never shown uncommented"
    for line in re.findall(r"^APPLYFIRST_ALERT_WEBHOOK=(\S+)", readme, re.M):
        assert line.startswith("<") and line.endswith(">"), (
            "a placeholder that is not in <...> would count as a real webhook when pasted")


def test_oracle_keeps_its_own_backup_timer():
    for unit in ("applyfirst-saas-worker.service", "applyfirst-saas-web.service"):
        assert "APPLYFIRST_BACKUP_IN_WORKER" not in (ORACLE / unit).read_text(encoding="utf-8"), (
            "the Oracle timer already backs up; a second daily backup halves the history")
