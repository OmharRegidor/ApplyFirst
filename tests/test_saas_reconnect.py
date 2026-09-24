"""B6. A user whose Gmail connection Google ends is told so by email, once, and only then.

While the app is in Google's Testing mode every refresh token dies 7 days after the user connects.
The worker clears the credential on the next send, and before B6 the user then simply stopped
receiving anything. These pin that the user is emailed at their own address, once per ended
connection, never after disconnecting on purpose, never after reconnecting mid-send, and that a
missing or broken mail server is loud to the owner without ever costing a cycle, giving up on
everyone, or leaking the SMTP password or a user's address.

The mail server is faked at smtplib.SMTP_SSL, so the real message building and the real split
between "connecting or logging in" and "handing over this message" both run.

Nothing here sets a real secret, touches the network or sleeps.
"""

from __future__ import annotations

import dataclasses
import logging
import smtplib
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from applyfirst.saas import app as app_module
from applyfirst.saas import db, gmail_send, google_oauth, notify, reconnect, session, worker
from test_saas_ops import _all_log_text, _events, _isolated_env, _prod
from test_saas_worker import FakeSource, _engine_factory, _raw, _seed

PW = "pw-s3cr3t-9f8e7d"
KEY = reconnect._PREFIX
T0 = 1_800_000_000.0
STAMP = "2026-09-01T00:00:00Z"


def _smtp(cfg, **kw):
    return dataclasses.replace(cfg, smtp_host="smtp.test", smtp_port=465,
                               smtp_user="agad@mail.test", smtp_password=PW, **kw)


class Mailbox:
    """Stands in for the server behind smtplib.SMTP_SSL and records every message it takes.

    ``fail`` refuses every message handed over, ``fail_for[address]`` one recipient's, and
    ``fail_at["connect" | "login" | "quit"]`` fails that stage. ``connects`` counts connections,
    ``tries`` messages handed over, ``order`` their recipients.
    """

    def __init__(self, monkeypatch):
        self.sent, self.order, self.connects, self.tries = [], [], 0, 0
        self.fail, self.fail_for, self.fail_at = None, {}, {}
        box = self

        class FakeServer:
            def __init__(self, host, port, context=None, timeout=None):
                box.connects += 1
                if "connect" in box.fail_at:
                    raise box.fail_at["connect"]
                self.host = host

            def login(self, user, password):
                if "login" in box.fail_at:
                    raise box.fail_at["login"]
                self.user, self.password = user, password

            def send_message(self, msg):
                box.tries += 1
                box.order.append(msg["To"])
                error = box.fail_for.get(msg["To"], box.fail)
                if error is not None:
                    raise error
                box.sent.append({"host": self.host, "user": self.user, "sender": msg["From"],
                                 "recipient": msg["To"], "subject": msg["Subject"],
                                 "text": msg.get_content()})

            def quit(self):
                if "quit" in box.fail_at:
                    raise box.fail_at["quit"]

            def close(self):
                pass

        monkeypatch.setattr(smtplib, "SMTP_SSL", FakeServer)


@pytest.fixture
def mailbox(monkeypatch):
    return Mailbox(monkeypatch)


@pytest.fixture
def owner(monkeypatch):
    """Every owner alert, as (subject, body)."""
    calls = []
    monkeypatch.setattr(notify, "send_owner_alert",
                        lambda cfg, subject, body: calls.append((subject, body)) or True)
    return calls


def _revoked(cfg, refresh, **kw):
    raise gmail_send.GmailAuthError("invalid_grant")


def _cycle(conn, cfg, master_key, sender=_revoked, jobs=("1",)):
    return worker.run_once(conn, FakeSource([_raw(j) for j in jobs]), cfg, master_key,
                           engine_factory=_engine_factory, sender=sender, polite=False)


def _baselined(conn, cfg, master_key, **seed):
    """A connected, activated user whose keyword has been polled once, so the next job alerts."""
    u = _seed(conn, master_key, **seed)
    _cycle(conn, cfg, master_key, sender=lambda *a, **k: "m", jobs=("0",))
    return u


def _state(conn, user_id):
    return db.get_worker_meta(conn, KEY + user_id)


def _is_due(conn, user_id, since="-"):
    parts = (_state(conn, user_id) or "").split(" ")
    return parts[:2] == ["due", STAMP] and (parts[2] if len(parts) > 2 else "-") == since


def _statuses(conn):
    return sorted(r["status"] for r in conn.execute("SELECT status FROM user_job_alerts"))


def _due_three(conn, master_key):
    """Three users owed an email, sorted by id (the order send_due tries never-tried rows)."""
    ids = [_seed(conn, master_key, sub=f"g{i}", email=f"u{i}@x.test").id for i in range(3)]
    for uid in ids:
        reconnect.expired(conn, uid, STAMP)
        db.clear_gmail_credential(conn, uid)
    return [db.get_user(conn, uid) for uid in sorted(ids)]


# --- the email itself ---------------------------------------------------------------------------

def test_an_ended_connection_emails_the_user_once_at_their_own_address(
        saas_cfg, master_key, mailbox, owner):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key, email="maria@inbox.test")
    connected_at = db.gmail_connected_at(conn, u.id)

    r = _cycle(conn, cfg, master_key)
    assert r.failed == 1 and r.reconnect_mailed == 1
    assert db.gmail_connected(conn, u.id) is False            # the old behaviour still holds
    assert len(mailbox.sent) == 1
    mail = mailbox.sent[0]
    assert mail["recipient"] == "maria@inbox.test"             # the user's own address
    assert mail["sender"] == "Agad <agad@mail.test>"           # the server's, never theirs
    assert mail["host"] == "smtp.test" and mail["user"] == "agad@mail.test"
    assert mail["subject"] == reconnect.SUBJECT
    assert "https://localhost:8000/dashboard" in mail["text"]
    assert _state(conn, u.id) == f"sent {connected_at}"

    # New jobs keep coming. Each is skipped for the missing Gmail, and nobody is mailed again.
    for jobs in (("2",), ("3", "4")):
        _cycle(conn, cfg, master_key, jobs=jobs)
    assert len(mailbox.sent) == 1
    assert owner == []
    conn.close()


def test_two_auth_errors_on_the_same_connection_send_one_email(
        saas_cfg, master_key, mailbox, monkeypatch):
    """If clearing the credential fails, the next alert meets the same dead grant again."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)
    real, calls = reconnect.clear_dead_grant, []

    def locked_twice(*a):
        calls.append(1)
        if len(calls) <= 2:
            raise RuntimeError("database is locked")
        return real(*a)

    monkeypatch.setattr(reconnect, "clear_dead_grant", locked_twice)
    _cycle(conn, cfg, master_key, jobs=("1", "2"))   # both alerts hit the dead grant
    _cycle(conn, cfg, master_key, jobs=("3",))
    assert _statuses(conn) == ["failed", "failed", "skipped"]
    assert len(mailbox.sent) == 1 and _state(conn, u.id).startswith("sent ")
    conn.close()


def test_the_email_waits_until_the_dead_grant_is_cleared(saas_cfg, master_key, mailbox,
                                                        monkeypatch):
    """While the dead grant is still stored the dashboard says Connected and hides the button
    the email points at, so the email waits for a cycle where clearing works."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)
    real = reconnect.clear_dead_grant

    def locked(*a):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(reconnect, "clear_dead_grant", locked)
    _cycle(conn, cfg, master_key)
    assert db.gmail_connected(conn, u.id) is True and mailbox.tries == 0
    assert _state(conn, u.id).startswith("due ")
    monkeypatch.setattr(reconnect, "clear_dead_grant", real)
    _cycle(conn, cfg, master_key, sender=lambda *a, **k: "m", jobs=("2",))
    assert db.gmail_connected(conn, u.id) is False and len(mailbox.sent) == 1
    conn.close()


def test_a_failure_while_queueing_never_drops_the_user(saas_cfg, master_key, mailbox, monkeypatch):
    """The email is queued before the dead grant is cleared. If queueing fails, the grant is still
    there, so the next alert meets it again instead of the user being skipped untold forever."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)
    real, calls = reconnect.expired, []

    def locked_once(*a):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database is locked")
        return real(*a)

    monkeypatch.setattr(reconnect, "expired", locked_once)
    _cycle(conn, cfg, master_key)
    assert db.gmail_connected(conn, u.id) is True and mailbox.tries == 0   # kept, for next time
    _cycle(conn, cfg, master_key, jobs=("2",))
    assert db.gmail_connected(conn, u.id) is False
    assert [m["recipient"] for m in mailbox.sent] == [u.email]
    conn.close()


def test_a_reconnect_between_the_check_and_the_clear_keeps_the_new_grant(
        saas_cfg, master_key, mailbox, monkeypatch):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)
    real = reconnect.expired

    def reconnect_lands_now(conn_, user_id, connected_at):
        queued = real(conn_, user_id, connected_at)          # the check already passed
        monkeypatch.setattr(db, "_now_iso", lambda: "2099-01-01T00:00:00Z")
        db.store_gmail_credential(conn_, user_id, refresh_token="rt-new", master_key=master_key)
        return queued                                        # forget() has not run yet

    monkeypatch.setattr(reconnect, "expired", reconnect_lands_now)
    _cycle(conn, cfg, master_key)
    assert db.get_gmail_refresh_token(conn, u.id, master_key) == "rt-new"
    assert _statuses(conn) == ["pending"] and mailbox.tries == 0
    assert _state(conn, u.id) is None          # the stale row was dropped, not mailed
    conn.close()


def test_the_next_connection_that_ends_is_news_again(saas_cfg, master_key):
    conn = db.init_db(saas_cfg.db_path)
    uid = _seed(conn, master_key).id
    later = "2026-09-08T00:00:00Z"
    assert reconnect.expired(conn, uid, STAMP) is True
    db.set_worker_meta(conn, KEY + uid, f"due {STAMP} 1700000000.0 1700000100.0")
    assert reconnect.expired(conn, uid, STAMP) is True            # clocks kept
    assert _state(conn, uid) == f"due {STAMP} 1700000000.0 1700000100.0"
    db.set_worker_meta(conn, KEY + uid, f"sent {STAMP}")
    assert reconnect.expired(conn, uid, STAMP) is False           # same connection
    db.set_worker_meta(conn, KEY + uid, f"refused {STAMP}")
    assert reconnect.expired(conn, uid, STAMP) is False
    assert reconnect.expired(conn, uid, later) is True            # a later one
    assert _state(conn, uid) == f"due {later}"
    reconnect.disconnected_on_purpose(conn, uid, later)
    assert reconnect.expired(conn, uid, later) is False           # that grant, off on purpose
    # A reconnect whose forget() never ran leaves "off" behind. It must not hide the next expiry.
    assert reconnect.expired(conn, uid, "2026-09-15T00:00:00Z") is True
    conn.close()


def test_the_copy_is_plain_true_and_short(saas_cfg):
    user = db.User(id="u", google_sub="g", email="m@x", display_name="Maria Santos",
                   plan="free", created_at=STAMP)
    subject, text = reconnect.compose(saas_cfg, user)
    assert subject == "Reconnect Gmail to keep getting job applications"
    assert text.startswith("Hi Maria,\n")
    assert "We never read your email." in text
    assert "Google asks everyone to reconnect every 7 days" in text    # Google's rule, said so
    assert "If you disconnected on purpose, you can ignore this email." in text
    assert f"{saas_cfg.base_url}/dashboard\n" in text                 # a literal, signed-out safe
    for banned in ("—", "–", "apply for you", "on your behalf", "guarantee",
                   "we applied"):
        assert banned not in text.lower() and banned not in subject.lower()
    assert len(text.split()) < 100                                    # one phone screen
    for blank in (None, "", "   "):
        assert reconnect.compose(saas_cfg, dataclasses.replace(user, display_name=blank)
                                 )[1].startswith("Hi there,\n")


# --- never for the wrong reason -----------------------------------------------------------------

def test_a_user_who_disconnects_on_purpose_gets_nothing(saas_cfg, master_key, mailbox, monkeypatch):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)
    connected_at = db.gmail_connected_at(conn, u.id)
    c = TestClient(app_module.create_app(cfg), follow_redirects=False)
    c.cookies.set("applyfirst_session", session.sign(cfg.session_secret, {"uid": u.id}))
    c.headers["X-CSRF-Token"] = session.issue_csrf(cfg.session_secret, u.id)
    seen = {}
    monkeypatch.setattr(google_oauth, "revoke_token",
                        lambda t: seen.setdefault("at_revoke", _state(conn, u.id)))
    assert c.post("/auth/disconnect-gmail").status_code == 302
    assert seen["at_revoke"] == f"off {connected_at}"   # marked BEFORE the grant is revoked
    _cycle(conn, cfg, master_key)
    assert mailbox.tries == 0 and _state(conn, u.id) == f"off {connected_at}"
    conn.close()


def test_a_send_that_dies_on_the_users_own_disconnect_is_not_called_an_expiry(
        saas_cfg, master_key, mailbox):
    """The web app revokes the grant while the worker is sending with it. Google answers
    invalid_grant, exactly as for an expiry, before or after the row is deleted."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)
    u_at = db.gmail_connected_at(conn, u.id)

    def revoked_mid_send(cfg_, refresh, **kw):      # marked and revoked, row not yet deleted
        reconnect.disconnected_on_purpose(conn, u.id, u_at)
        raise gmail_send.GmailAuthError("invalid_grant")

    _cycle(conn, cfg, master_key, sender=revoked_mid_send)
    assert _state(conn, u.id) == f"off {u_at}"

    u2 = _seed(conn, master_key, sub="g2", email="b@x")
    u2_at = db.gmail_connected_at(conn, u2.id)

    def removed_mid_send(cfg_, refresh, **kw):      # and the row already gone
        reconnect.disconnected_on_purpose(conn, u2.id, u2_at)
        db.clear_gmail_credential(conn, u2.id)
        raise gmail_send.GmailAuthError("invalid_grant")

    _cycle(conn, cfg, master_key, sender=removed_mid_send, jobs=("2",))
    assert _state(conn, u2.id) == f"off {u2_at}"
    assert mailbox.tries == 0
    conn.close()


def test_a_reconnect_during_the_send_keeps_the_new_grant(saas_cfg, master_key, mailbox,
                                                         monkeypatch):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)

    def reconnected_mid_send(cfg_, refresh, **kw):
        monkeypatch.setattr(db, "_now_iso", lambda: "2099-01-01T00:00:00Z")
        db.store_gmail_credential(conn, u.id, refresh_token="rt-new", master_key=master_key)
        raise gmail_send.GmailAuthError("invalid_grant")     # the OLD token

    r = _cycle(conn, cfg, master_key, sender=reconnected_mid_send)
    assert db.get_gmail_refresh_token(conn, u.id, master_key) == "rt-new"   # not cleared
    assert _statuses(conn) == ["pending"] and r.failed == 0                 # retried with it
    assert mailbox.tries == 0 and _state(conn, u.id) is None

    sent = []
    _cycle(conn, cfg, master_key, sender=lambda c, rt, **kw: sent.append(rt) or "m")
    assert sent == ["rt-new"] and _statuses(conn) == ["sent"]
    conn.close()


def test_reconnecting_through_google_clears_what_is_owed(saas_cfg, master_key, monkeypatch):
    conn = db.init_db(saas_cfg.db_path)
    u = db.upsert_user_by_google(conn, google_sub="g", email="u@x", display_name="U")
    db.set_worker_meta(conn, KEY + u.id, f"due {STAMP}")
    c = TestClient(app_module.create_app(saas_cfg), follow_redirects=False)
    c.cookies.set("applyfirst_session", session.sign(saas_cfg.session_secret, {"uid": u.id}))
    state = parse_qs(urlparse(c.get("/auth/connect-gmail").headers["location"]).query)["state"][0]
    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail", lambda cfg, **kw: "rt")
    assert c.get("/auth/gmail-callback", params={"code": "c", "state": state}).status_code == 302
    assert _state(conn, u.id) is None
    conn.close()


def test_a_user_back_on_gmail_before_the_mail_goes_is_not_mailed(
        saas_cfg, master_key, mailbox, owner, monkeypatch):
    """No mail server at the expiry. By the time there is one, the user has reconnected."""
    conn = db.init_db(saas_cfg.db_path)
    u = _baselined(conn, saas_cfg, master_key)
    _cycle(conn, saas_cfg, master_key)
    assert _state(conn, u.id).startswith("due ")
    monkeypatch.setattr(db, "_now_iso", lambda: "2099-01-01T00:00:00Z")   # days later
    db.store_gmail_credential(conn, u.id, refresh_token="rt2", master_key=master_key)
    _cycle(conn, _smtp(saas_cfg), master_key, sender=lambda *a, **k: "m", jobs=("2",))
    assert mailbox.tries == 0 and _state(conn, u.id) is None
    assert db.get_gmail_refresh_token(conn, u.id, master_key) == "rt2"   # the new grant stays
    conn.close()


# --- no mail server, or a broken one --------------------------------------------------------------

def test_no_smtp_logs_pages_the_owner_once_and_mails_once_it_is_set(
        saas_cfg, master_key, mailbox, owner, caplog):
    conn = db.init_db(saas_cfg.db_path)
    u = _baselined(conn, saas_cfg, master_key)
    with caplog.at_level(logging.INFO, logger="applyfirst"):
        r = _cycle(conn, saas_cfg, master_key)
        _cycle(conn, saas_cfg, master_key, jobs=("2",))
    assert r.failed == 1 and r.reconnect_mailed == 0
    assert len(_events(caplog, "user_reconnect_email_skipped", logging.ERROR)) == 1
    assert [s for s, _ in owner] == ["Agad cannot tell users to reconnect Gmail"]   # debounced
    assert u.email not in owner[0][1]                        # the owner learns a count, not who
    assert _state(conn, u.id).startswith("due ")

    r = _cycle(conn, _smtp(saas_cfg), master_key, jobs=("3",))
    assert r.reconnect_mailed == 1 and [m["recipient"] for m in mailbox.sent] == [u.email]
    conn.close()


def test_a_bad_login_pauses_alerts_and_never_logs_the_password(
        saas_cfg, master_key, mailbox, owner, caplog):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    u = _baselined(conn, cfg, master_key)
    mailbox.fail_at["login"] = smtplib.SMTPAuthenticationError(
        535, f"bad login agad@mail.test/{PW}".encode())
    with caplog.at_level(logging.INFO, logger="applyfirst"):
        r = _cycle(conn, cfg, master_key)
    assert r.reconnect_mailed == 0 and _state(conn, u.id).startswith("due ")
    assert _events(caplog, "user_reconnect_email_failed", logging.ERROR)
    assert PW not in _all_log_text(caplog)
    assert [s for s, _ in owner] == ["Agad's reconnect emails are failing"]
    assert PW not in owner[0][1] and "<password>" in owner[0][1]
    assert "connecting or logging in" in owner[0][1]

    mailbox.fail_at.clear()
    r = _cycle(conn, cfg, master_key, jobs=("2",))
    assert r.reconnect_mailed == 0 and mailbox.connects == 1   # paused: no login every cycle
    reconnect.reset_backoff(conn)       # the owner fixes the password and restarts the worker
    r = _cycle(conn, cfg, master_key, jobs=("3",))
    assert r.reconnect_mailed == 1 and len(mailbox.sent) == 1
    assert _state(conn, u.id).startswith("sent ")
    conn.close()


def test_a_broken_smtp_account_is_not_reported_through_itself(
        saas_cfg, master_key, mailbox, owner, caplog):
    """With SMTP as the owner's alert channel, the alert would ride the same failing login."""
    cfg = _smtp(saas_cfg, owner_alert_email="owner@x.test")
    assert cfg.alert_channel == "smtp"
    conn = db.init_db(cfg.db_path)
    _baselined(conn, cfg, master_key)
    mailbox.fail_at["login"] = smtplib.SMTPAuthenticationError(535, b"bad login")
    with caplog.at_level(logging.INFO, logger="applyfirst"):
        _cycle(conn, cfg, master_key)
    assert "Agad's reconnect emails are failing" not in [s for s, _ in owner]
    assert _events(caplog, "user_reconnect_mail_down", logging.CRITICAL)
    assert mailbox.connects == 1
    conn.close()


@pytest.mark.parametrize("stage,server_says", [
    ("connect", OSError("connection refused")),
    ("connect", UnicodeError("encoding with 'idna' codec failed (label empty)")),
    ("login", smtplib.SMTPAuthenticationError(534, b"5.7.9 Application-specific password required")),
    ("login", smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")),
    ("login", UnicodeEncodeError("ascii", "\0agad\0contraseña", 13, 14, "not in range")),
    ("send", smtplib.SMTPRecipientsRefused({"u0@x.test": (421, b"4.7.0 Try again later")})),
    ("send", smtplib.SMTPDataError(421, b"4.7.0 Try again later, closing")),
    ("send", smtplib.SMTPSenderRefused(553, b"5.1.8 Sender rejected", "agad@mail.test")),
    ("send", smtplib.SMTPServerDisconnected("Connection unexpectedly closed")),
], ids=["no-connection", "host-typo", "app-password", "no-auth", "non-ascii-password",
        "rcpt-421", "data-421", "sender-refused", "disconnected"])
def test_a_server_fault_pauses_and_never_gives_anyone_up(
        saas_cfg, master_key, mailbox, stage, server_says):
    """Anything while connecting or logging in, a 421 or a dropped line is the server's. One
    connection ends the round, everyone stays owed with no refusal clock, and sending pauses."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    users = _due_three(conn, master_key)
    if stage == "send":
        mailbox.fail = server_says
    else:
        mailbox.fail_at[stage] = server_says
    out = reconnect.send_due(conn, cfg, now=T0)
    assert out.failed and out.rejected == 0 and mailbox.connects == 1
    assert all(_is_due(conn, u.id) for u in users)
    assert "ñ" not in out.failed and "position" not in out.failed   # no password character
    mailbox.fail, mailbox.fail_at = None, {}
    assert reconnect.send_due(conn, cfg, now=T0 + 60).paused and mailbox.connects == 1
    assert reconnect.send_due(conn, cfg, now=T0 + 16 * 60).sent == 3
    conn.close()


def test_the_pause_grows_a_success_ends_it_and_an_old_one_is_forgotten(
        saas_cfg, master_key, mailbox):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    _due_three(conn, master_key)
    mailbox.fail_at["connect"] = OSError("connection refused")
    t = T0
    for pause in (15 * 60, 3600, 6 * 3600, 6 * 3600):          # then it stays at 6 hours
        connects = mailbox.connects
        assert reconnect.send_due(conn, cfg, now=t).failed and mailbox.connects == connects + 1
        assert reconnect.send_due(conn, cfg, now=t + pause - 1).paused
        assert mailbox.connects == connects + 1
        t += pause
    # Quiet for a week, then one more fault: the pause starts short again.
    t += 7 * 86400
    reconnect.send_due(conn, cfg, now=t)
    assert db.get_worker_meta(conn, reconnect._BACKOFF_KEY).endswith(" 0")
    mailbox.fail_at.clear()
    assert reconnect.send_due(conn, cfg, now=t + 15 * 60).sent == 3
    assert db.get_worker_meta(conn, reconnect._BACKOFF_KEY) is None
    conn.close()


def test_a_restart_ends_the_pause(saas_cfg, owner):
    conn = db.init_db(saas_cfg.db_path)
    db.set_worker_meta(conn, reconnect._BACKOFF_KEY, f"{T0 + 9e9} 2")
    worker._startup_checks(conn, saas_cfg)
    assert db.get_worker_meta(conn, reconnect._BACKOFF_KEY) is None
    conn.close()


@pytest.mark.parametrize("make", [
    lambda to: smtplib.SMTPRecipientsRefused(
        {to: (550, f"5.1.1 <{to}>: Recipient address rejected".encode())}),
    lambda to: smtplib.SMTPRecipientsRefused({to: (452, f"4.2.2 {to} mailbox full".encode())}),
    lambda to: smtplib.SMTPDataError(554, f"5.7.1 Message to {to.upper()} rejected".encode()),
], ids=["rcpt-550", "rcpt-452-lasting", "data-554"])
def test_one_refused_message_holds_nobody_up_and_is_given_up_after_3_days(
        saas_cfg, master_key, mailbox, caplog, make):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    first, *rest = _due_three(conn, master_key)
    mailbox.fail_for[first.email] = make(first.email)
    with caplog.at_level(logging.INFO, logger="applyfirst"):
        out = reconnect.send_due(conn, cfg, now=T0)
    assert out.sent == 2 and out.rejected == 1 and out.failed is None     # no pause for this
    assert sorted(m["recipient"] for m in mailbox.sent) == sorted(u.email for u in rest)
    assert db.get_worker_meta(conn, reconnect._BACKOFF_KEY) is None
    assert first.email.lower() not in _all_log_text(caplog).lower()      # servers quote it
    assert first.email.lower() not in out.rejected_error.lower()
    assert "<user>" in out.rejected_error
    assert _is_due(conn, first.id, since=str(T0))
    reconnect.send_due(conn, cfg, now=T0 + 86400)                          # retried, clock kept
    assert mailbox.tries == 4 and _is_due(conn, first.id, since=str(T0))
    out = reconnect.send_due(conn, cfg, now=T0 + 3 * 86400)
    assert mailbox.tries == 5 and out.gave_up == 1
    assert _state(conn, first.id) == f"refused {STAMP}"
    reconnect.send_due(conn, cfg, now=T0 + 4 * 86400)
    assert mailbox.tries == 5                                              # given up for good
    conn.close()


def test_a_refusal_that_hits_everyone_pauses_and_gives_nobody_up(saas_cfg, master_key, mailbox):
    """A daily quota or a relay rule refuses every message. Two refusals in a row look like the
    server, and nobody is given up while no message at all is going through."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    users = _due_three(conn, master_key)
    mailbox.fail = smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded")
    out = reconnect.send_due(conn, cfg, now=T0)
    assert mailbox.tries == 2 and out.failed and out.rejected == 1     # the third was spared
    t = T0
    for _ in range(40):                                                # well past 3 days
        t += 6 * 3600 + 1
        reconnect.send_due(conn, cfg, now=t)
    assert all(_state(conn, u.id).startswith("due ") for u in users)
    mailbox.fail = None
    assert reconnect.send_due(conn, cfg, now=t + 6 * 3600 + 1).sent == 3
    conn.close()


def test_the_least_recently_tried_goes_first(saas_cfg, master_key, mailbox):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    a, b, c = _due_three(conn, master_key)
    db.set_worker_meta(conn, KEY + a.id, f"due {STAMP} - {T0 + 5}")
    db.set_worker_meta(conn, KEY + c.id, f"due {STAMP} - {T0}")
    reconnect.send_due(conn, cfg, now=T0 + 60)
    assert mailbox.order == [b.email, c.email, a.email]
    conn.close()


def test_a_bad_reply_after_the_message_went_is_not_a_failure(saas_cfg, master_key, mailbox,
                                                             monkeypatch, capsys):
    """The server took the message, then answered QUIT badly. Retrying would send it again."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    users = _due_three(conn, master_key)
    mailbox.fail_at["quit"] = smtplib.SMTPResponseException(500, b"5.5.1 bad QUIT")
    out = reconnect.send_due(conn, cfg, now=T0)
    assert out.sent == 3 and out.failed is None
    assert all(_state(conn, u.id).startswith("sent ") for u in users)
    conn.close()


def test_the_owner_hears_about_refusals_and_give_ups_in_their_own_words(
        saas_cfg, owner, monkeypatch):
    conn = db.init_db(saas_cfg.db_path)
    monkeypatch.setattr(reconnect, "send_due", lambda *a, **k: reconnect.Outcome(
        rejected=1, rejected_error="SMTPRecipientsRefused: <user> 550", gave_up=1))
    worker._tell_expired_users(conn, _smtp(saas_cfg), lambda: None)
    subjects = [s for s, _ in owner]
    assert subjects == ["Agad's reconnect email to a user was refused",
                        "Agad gave up telling a user to reconnect Gmail"]
    assert "pauses" not in owner[0][1] and "login works" in owner[0][1]
    conn.close()


@pytest.mark.parametrize("owner_email", [None, "owner@x.test"], ids=["webhook", "smtp-alerts"])
def test_a_paused_round_reports_only_the_pause(saas_cfg, master_key, mailbox, owner, owner_email):
    """Every message refused: the round pauses. The owner must not also read that the login
    works and other users are still being emailed. And the login did work, so even with SMTP as
    the alert channel the alert is tried, not held back as a broken account."""
    cfg = _smtp(saas_cfg, owner_alert_email=owner_email)
    conn = db.init_db(cfg.db_path)
    _due_three(conn, master_key)
    mailbox.fail = smtplib.SMTPDataError(550, b"5.7.1 Message rejected as unsolicited")
    worker._tell_expired_users(conn, cfg, lambda: None)
    assert [s for s, _ in owner] == ["Agad's reconnect emails are failing"]
    conn.close()


def test_a_lone_refused_message_is_not_resent_every_cycle(saas_cfg, master_key, mailbox):
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    first, *rest = _due_three(conn, master_key)
    for u in rest:
        db.set_worker_meta(conn, KEY + u.id, f"sent {STAMP}")
    mailbox.fail_for[first.email] = smtplib.SMTPDataError(550, b"5.4.5 Daily limit exceeded")
    t = T0
    while t < T0 + 86400:                                    # a day at the Oracle cadence
        reconnect.send_due(conn, cfg, now=t)
        t += 330
    assert mailbox.tries < 40                                # not 262
    assert db.get_worker_meta(conn, reconnect._BACKOFF_KEY) is None   # nobody else was held up
    conn.close()


def test_a_message_accepted_before_the_refusal_proves_nothing(saas_cfg, master_key, mailbox):
    """Give-up needs a message that went through AFTER this one was first refused. One sent
    earlier in the same round, just before the server started refusing, does not count."""
    cfg = _smtp(saas_cfg)
    conn = db.init_db(cfg.db_path)
    a, b, c = _due_three(conn, master_key)
    db.set_worker_meta(conn, KEY + c.id, f"sent {STAMP}")
    mailbox.fail_for[b.email] = smtplib.SMTPDataError(554, b"5.7.1 Rejected")
    out = reconnect.send_due(conn, cfg, now=T0)                # a goes, then b is refused
    assert out.sent == 1 and out.rejected == 1
    for day in range(1, 5):
        reconnect.send_due(conn, cfg, now=T0 + day * 86400)
    assert _state(conn, b.id).startswith("due ")             # never given up on that proof
    conn.close()


def test_a_crash_in_the_notice_never_costs_the_cycle(saas_cfg, master_key, monkeypatch, caplog):
    conn = db.init_db(saas_cfg.db_path)
    _baselined(conn, saas_cfg, master_key)

    def boom(*a, **k):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(reconnect, "send_due", boom)
    sent = []
    with caplog.at_level(logging.INFO, logger="applyfirst"):
        r = _cycle(conn, saas_cfg, master_key, sender=lambda *a, **k: sent.append(1) or "m")
    assert r.sent == 1 and sent == [1]
    assert _events(caplog, "user_reconnect_round_failed", logging.ERROR)
    assert _events(caplog, "cycle_complete")
    conn.close()


# --- set-up and the owner's view ------------------------------------------------------------------

def test_the_settings_check_sends_the_real_email(saas_cfg, mailbox, monkeypatch, capsys):
    from applyfirst import log
    monkeypatch.setattr(log, "configure", lambda *a, **k: None)
    cfg = {"now": saas_cfg}
    monkeypatch.setattr("applyfirst.saas.config.load_saas_config", lambda: cfg["now"])
    assert reconnect.main(["--test", "me@x.test"]) == 1
    assert "not configured" in capsys.readouterr().out

    cfg["now"] = _smtp(saas_cfg)
    assert reconnect.main(["--test", "me@x.test"]) == 0
    assert "sent to me@x.test" in capsys.readouterr().out
    assert mailbox.sent[0]["recipient"] == "me@x.test"
    assert mailbox.sent[0]["subject"] == reconnect.SUBJECT

    mailbox.fail_at["quit"] = smtplib.SMTPResponseException(500, b"bad QUIT")
    assert reconnect.main(["--test", "me@x.test"]) == 0          # it went, so it passed
    capsys.readouterr()

    mailbox.fail_at = {"login": smtplib.SMTPAuthenticationError(535, f"bad {PW}".encode())}
    assert reconnect.main(["--test", "me@x.test"]) == 1
    out = capsys.readouterr().out
    assert "failed: connecting or logging in" in out and PW not in out
    assert reconnect.main([]) == 2


def test_user_mail_needs_host_user_and_password_but_not_an_owner_address(saas_cfg, monkeypatch):
    assert saas_cfg.user_mail_configured is False
    assert _smtp(saas_cfg).user_mail_configured is True
    assert _smtp(saas_cfg).alert_channel is None             # owner alerts still need their address
    for missing in ("smtp_host", "smtp_user", "smtp_password"):
        assert dataclasses.replace(_smtp(saas_cfg), **{missing: None}).user_mail_configured is False
    cfg = _isolated_env(monkeypatch, APPLYFIRST_SMTP_HOST="smtp.x", APPLYFIRST_SMTP_USER="u@x",
                        APPLYFIRST_SMTP_PASSWORD="<gmail-app-password>")
    assert cfg.user_mail_configured is False                 # an unfilled sample line is missing


def test_a_production_worker_without_smtp_says_so_at_start(saas_cfg, owner, caplog):
    conn = db.init_db(saas_cfg.db_path)
    with caplog.at_level(logging.INFO, logger="applyfirst"):
        worker._startup_checks(conn, _prod(saas_cfg, ai_off_ok=True))
    assert _events(caplog, "user_mail_not_configured", logging.ERROR)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="applyfirst"):
        worker._startup_checks(conn, _prod(_smtp(saas_cfg), ai_off_ok=True))
        worker._startup_checks(conn, saas_cfg)                # a development box is left alone
    assert not _events(caplog, "user_mail_not_configured")
    conn.close()


def test_the_privacy_page_says_it_may_email_about_the_account(saas_cfg):
    from _saas_client import client_for, page_text
    text = page_text(client_for(saas_cfg).get("/privacy").text)
    assert "tell you that your Gmail connection has ended and needs reconnecting" in text
    assert "never marketing" in text
