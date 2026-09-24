"""B6. Tell a user by email when Google ends their Gmail connection.

While the Google app is in Testing mode, Google expires every refresh token 7 days after the user
connects. The worker finds out on the next send (``GmailAuthError``) and clears the credential.
Before this module the user then stopped receiving anything and nobody told them.

Their own Gmail cannot carry the news, because that grant is exactly what just died. It goes out
through the server-owned SMTP settings instead (``APPLYFIRST_SMTP_HOST/PORT/USER/PASSWORD``, the
same ones owner alerts can use), to the address the user signed in with.

One ``worker_meta`` row per user holds the state, so there is no schema change:

    reconnect_mail_<user_id> = "due <connected_at> <since> <tried>"   waiting to go out
                               "sent <connected_at>"                  went out
                               "refused <connected_at>"               given up (see below)
                               "off <connected_at>"                   the user disconnected
                                                                      that grant on purpose

``connected_at`` is when the credential that died was stored, so each ended connection is mailed
about once, and the next one that ends is news again. ``since`` is when the server first refused
this message ("-" if it never has), ``tried`` the last attempt, so the least recently tried user
goes first and one stuck address can never hold up the rest.

Once means at least once, normally exactly once. If the mail server takes the message but its
reply is lost, or the worker stops at that moment, the row still says due and it goes again. A
second copy of this notice is a far smaller harm than a user never told.

Failures come in two kinds, told apart by WHEN they happen, not by guessing from a reply code:
- Anything while connecting or logging in, a 421, or a dropped connection is the server's. The
  round stops and sending pauses for 15 minutes, then an hour, then 6 hours, so a wrong password
  does not log in to the owner's mail account every cycle all day. A restart ends the pause.
- A refusal of the message itself is this user's. The others still go, and that message is
  retried on its own slower clock (every 15 minutes, then hourly, then every 6 hours). Two in a
  row in one round look like the server again (a quota, a relay rule) and pause it. A user is
  given up only after 3 days of refusals AND only if some other message went through after the
  first one, so a fault that hits every message can never retire everyone.

The worker writes due, sent and refused. The web app writes off before a deliberate disconnect and
deletes the row on a reconnect.

Check the settings before the first user needs them:
    python -m applyfirst.saas.reconnect --test you@example.com
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from applyfirst import log
from applyfirst.saas import db

_LOG = log.get_logger("saas.reconnect")
_PREFIX = "reconnect_mail_"
_BACKOFF_KEY = "reconnect_smtp_backoff"       # "<until epoch> <level>"; not under _PREFIX
_ACCEPTED_KEY = "reconnect_last_accepted"     # epoch of the last message the server took
_BACKOFF = (15 * 60, 3600, 6 * 3600)
_GIVE_UP_AFTER = 3 * 86400
_TIMEOUT = 30

SUBJECT = "Reconnect Gmail to keep getting job applications"


@dataclass(slots=True)
class Outcome:
    sent: int = 0
    waiting: int = 0                  # due, but there are no SMTP settings to send them with
    failed: str | None = None         # the server failed; sending is paused
    server_down: bool = False         # ...because connecting or logging in failed
    rejected: int = 0                 # messages the server refused this round
    rejected_error: str | None = None
    gave_up: int = 0                  # users given up this round
    paused: bool = False              # still inside a pause from an earlier failure


@dataclass(slots=True)
class _Row:
    state: str
    stamp: str
    since: float | None = None
    tried: float = 0.0


class _ServerDown(Exception):
    """Connecting or logging in failed, so nothing is known about any one message."""


def _key(user_id: str) -> str:
    return _PREFIX + user_id


def _num(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "", "-") else None
    except ValueError:
        return None


def _parse(value: str | None) -> _Row | None:
    if not value:
        return None
    parts = value.split(" ")
    return _Row(parts[0], parts[1] if len(parts) > 1 else "-",
                _num(parts[2]) if len(parts) > 2 else None,
                (_num(parts[3]) or 0.0) if len(parts) > 3 else 0.0)


def _row(conn, user_id: str) -> _Row | None:
    return _parse(db.get_worker_meta(conn, _key(user_id)))


def _write_due(conn, user_id: str, row: _Row, *, since: float | None, tried: float) -> None:
    db.set_worker_meta(conn, _key(user_id),
                       f"due {row.stamp} {since if since is not None else '-'} {tried}")


def expired(conn, user_id: str, connected_at: str | None) -> bool:
    """The worker found this user's grant dead, so queue the email. Returns True when it is due.

    Nothing is queued when the user disconnected this grant on purpose, or this very connection
    was already mailed about or given up on. One statement, so the web app's "off" can never land
    between the check and the write. A row already due for this connection keeps its clocks.
    """
    stamp = connected_at or "-"
    conn.execute(
        "INSERT INTO worker_meta (key, value) VALUES (?1, ?2) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value "
        "WHERE worker_meta.value NOT IN "
        "('off ' || ?3, 'sent ' || ?3, 'refused ' || ?3, 'due ' || ?3) "
        "AND worker_meta.value NOT LIKE 'due ' || ?3 || ' %'",
        (_key(user_id), f"due {stamp}", stamp))
    conn.commit()
    row = _row(conn, user_id)
    return row is not None and row.state == "due" and row.stamp == stamp


def disconnected_on_purpose(conn, user_id: str, connected_at: str | None) -> None:
    """Called by the web app BEFORE it revokes the grant. The revoke makes an in-flight send fail
    exactly like an expiry does, so this mark is what keeps that user from being told it expired.
    Tied to the grant being disconnected, so a later one that expires is news again."""
    db.set_worker_meta(conn, _key(user_id), f"off {connected_at or '-'}")


def forget(conn, user_id: str) -> None:
    """The user has a working grant again: nothing is owed."""
    # Inline on purpose: db.py (the data layer) is protected and has no delete for worker_meta.
    conn.execute("DELETE FROM worker_meta WHERE key=?", (_key(user_id),))
    conn.commit()


def clear_dead_grant(conn, user_id: str, connected_at: str) -> bool:
    """Delete the user's Gmail grant only if it is still the one that died. True if it was.

    ``db.clear_gmail_credential`` deletes whatever row is there, which would take a grant the user
    stored a moment ago. Inline on purpose: db.py (the data layer) is protected.
    """
    cur = conn.execute("DELETE FROM oauth_credentials "
                       "WHERE user_id=? AND provider='google' AND updated_at=?",
                       (user_id, connected_at))
    conn.commit()
    return cur.rowcount > 0


def reset_backoff(conn) -> None:
    """Send again at once. The worker calls this at start, because a restart usually follows a
    settings change, and after every message the server takes."""
    conn.execute("DELETE FROM worker_meta WHERE key=?", (_BACKOFF_KEY,))
    conn.commit()


def _backing_off(conn, now: float) -> bool:
    value = db.get_worker_meta(conn, _BACKOFF_KEY)
    until = _num(value.split(" ")[0]) if value else None
    return until is not None and now < until


def _retry_gap(age: float) -> float:
    """How long a refused message waits before its next try: 15 minutes in its first hour, then
    hourly for a day, then every 6 hours. Most rounds hold one user, so this, not the two-in-a-row
    rule, is what keeps a refusal from being resent every cycle."""
    return _BACKOFF[0] if age < 3600 else _BACKOFF[1] if age < 86400 else _BACKOFF[2]


def _back_off(conn, now: float) -> None:
    """Pause sending, a step longer than last time. A pause that ended long ago is forgotten, so
    the next fault a week later starts at 15 minutes again."""
    parts = (db.get_worker_meta(conn, _BACKOFF_KEY) or "").split(" ")
    until, level = _num(parts[0]), _num(parts[1]) if len(parts) > 1 else None
    fresh = until is None or level is None or now - until > _BACKOFF[-1]
    level = 0 if fresh else int(level) + 1
    delay = _BACKOFF[min(level, len(_BACKOFF) - 1)]
    db.set_worker_meta(conn, _BACKOFF_KEY, f"{now + delay} {level}")


def compose(cfg, user) -> tuple[str, str]:
    """The subject and plain-text body. Short enough to read on a phone, and true for every way
    a grant dies: the 7-day beta rule, a Google password change, or Agad removed at Google."""
    name = (user.display_name or "").split()
    link = f"{cfg.base_url}/dashboard"   # signs them in first if needed, then shows Connect Gmail
    text = (
        f"Hi {name[0] if name else 'there'},\n\n"
        "Your Gmail connection to Agad has ended, so new matches can't reach your inbox until "
        "you reconnect. It takes about 30 seconds:\n"
        f"{link}\n\n"
        # BETA: remove this sentence after Google verification
        "This usually happens because, while Agad is in beta, Google asks everyone to reconnect "
        "every 7 days. "
        # /BETA
        "If you disconnected on purpose, you can ignore this email.\n\n"
        "Agad only uses Gmail to send ready-to-paste applications to your own inbox. "
        "We never read your email.\n\n"
        "Agad\n"
    )
    return SUBJECT, text


def _send(cfg, to: str, subject: str, text: str) -> None:
    """Send one message. Raises ``_ServerDown`` for any failure before the message is handed over.

    Anything that goes wrong after the server has answered the message (a QUIT that is not 221,
    say) is ignored, because the message's fate is already decided and a retry would repeat it.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Agad", cfg.smtp_user)) if "@" in cfg.smtp_user else cfg.smtp_user
    msg["To"] = to
    msg.set_content(text)
    try:
        server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port,
                                  context=ssl.create_default_context(), timeout=_TIMEOUT)
    except Exception as exc:
        raise _ServerDown() from exc
    try:
        try:
            server.login(cfg.smtp_user, cfg.smtp_password)
        except Exception as exc:
            raise _ServerDown() from exc
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 — see the docstring
            server.close()


def _this_message_only(exc: Exception) -> bool:
    """True when the server refused this one message, so the others can still go. Everything
    else, including a 421 at any stage and a dropped connection, is the server's."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return all(code != 421 for code, _ in exc.recipients.values())
    if isinstance(exc, smtplib.SMTPDataError):
        return exc.smtp_code != 421
    return isinstance(exc, (smtplib.SMTPNotSupportedError, UnicodeError, ValueError))


def _describe(cfg, exc: Exception, to: str | None = None) -> str:
    """The error for a log line or an owner alert, with the SMTP password and the user's address
    taken out. Mail servers quote the recipient in their replies. Replaced before cutting, so a
    cut can never leave half of either behind."""
    where = "connecting or logging in: " if isinstance(exc, _ServerDown) else ""
    inner = exc.__cause__ if isinstance(exc, _ServerDown) and exc.__cause__ else exc
    if isinstance(inner, UnicodeError):
        # Its text quotes the offending character and where it sits, which can be the password's.
        text = (f"{where}{type(inner).__name__}: the SMTP host, user or password, or the "
                "address, has a character that cannot be sent")
    else:
        text = f"{where}{type(inner).__name__}: {inner}"
    if cfg.smtp_password:
        text = text.replace(cfg.smtp_password, "<password>")
    if to:
        text = re.sub(re.escape(to), "<user>", text, flags=re.IGNORECASE)
    return text[:200]


def _due(conn) -> list[tuple[str, _Row]]:
    """Every due row, least recently tried first."""
    rows = conn.execute(
        "SELECT key, value FROM worker_meta WHERE substr(key, 1, ?) = ? AND value LIKE 'due %'",
        (len(_PREFIX), _PREFIX)).fetchall()
    due = [(r["key"][len(_PREFIX):], _parse(r["value"])) for r in rows]
    return sorted(due, key=lambda item: (item[1].tried, item[0]))


def send_due(conn, cfg, *, beat=None, now: float | None = None) -> Outcome:
    """Email every user who is owed one. Never raises for a mail problem. See the module note."""
    beat = beat or (lambda: None)
    now = time.time() if now is None else now
    out = Outcome()
    refused_in_a_row = attempts = 0
    for user_id, _ in _due(conn):
        beat()
        row = _row(conn, user_id)             # re-read: the web app may have moved since
        if row is None or row.state != "due":
            continue
        user = db.get_user(conn, user_id)
        now_at = db.gmail_connected_at(conn, user_id)
        # Only a NEWER grant is a reconnect. The dead one can outlive a failed clear.
        if user is None or (now_at is not None and now_at != row.stamp):
            forget(conn, user_id)
            continue
        if now_at is not None:
            # The dead grant is still stored, so the dashboard would say "Connected" and hide the
            # button the email sends them to. Clear it first, or wait for a cycle where that works.
            try:
                clear_dead_grant(conn, user_id, row.stamp)
            except Exception as exc:  # noqa: BLE001
                log.event(_LOG, "user_reconnect_clear_failed", level=logging.WARNING,
                          user_id=user_id, error=str(exc)[:200])
                continue
        if not cfg.user_mail_configured:
            out.waiting += 1
            continue
        if row.since is not None and now - row.tried < _retry_gap(now - row.since):
            continue                          # refused before: its own slower clock
        if _backing_off(conn, now):
            out.paused = True
            break
        # Each attempt gets its own instant, so "accepted after this refusal" keeps its order
        # inside one round, where every attempt would otherwise share the same now.
        at = now + attempts / 1000
        attempts += 1
        try:
            _send(cfg, user.email, *compose(cfg, user))
        except Exception as exc:  # noqa: BLE001 — a mail problem must never stop the worker
            error = _describe(cfg, exc, user.email)
            refused_in_a_row += 1 if _this_message_only(exc) else 0
            if not _this_message_only(exc) or refused_in_a_row >= 2:
                # The server's fault, or the same wall twice running. Pause everyone.
                _write_due(conn, user_id, row, since=row.since, tried=at)
                _back_off(conn, now)
                out.failed = error
                out.server_down = isinstance(exc, _ServerDown)
                log.event(_LOG, "user_reconnect_email_failed", level=logging.ERROR,
                          user_id=user_id, error=error)
                break
            since = row.since if row.since is not None else at
            accepted = _num(db.get_worker_meta(conn, _ACCEPTED_KEY)) or 0.0
            gave_up = at - since >= _GIVE_UP_AFTER and accepted > since
            if gave_up:
                db.set_worker_meta(conn, _key(user_id), f"refused {row.stamp}")
                out.gave_up += 1
            else:
                _write_due(conn, user_id, row, since=since, tried=at)
            out.rejected += 1
            out.rejected_error = error
            log.event(_LOG, "user_reconnect_email_refused", level=logging.ERROR,
                      user_id=user_id, error=error, gave_up=gave_up)
            continue
        refused_in_a_row = 0
        db.set_worker_meta(conn, _key(user_id), f"sent {row.stamp}")
        db.set_worker_meta(conn, _ACCEPTED_KEY, str(at))
        reset_backoff(conn)
        log.event(_LOG, "user_reconnect_emailed", user_id=user_id)
        out.sent += 1
    return out


def main(argv: list[str] | None = None) -> int:
    """Send the reconnect email to one address, so the owner can see it arrive.

        python -m applyfirst.saas.reconnect --test you@example.com

    docs/OPERATIONS.md section 2 has the Fly and Oracle forms. Exit 0 only when the mail server
    took it. It goes the same way a real one does, so this is the only check of these settings:
    ``notify --test`` uses the webhook when one is set.
    """
    import argparse

    from applyfirst.saas.config import load_saas_config

    parser = argparse.ArgumentParser(prog="applyfirst.saas.reconnect")
    parser.add_argument("--test", metavar="ADDRESS",
                        help="send the reconnect email to ADDRESS and exit")
    args = parser.parse_args(argv)
    if not args.test:
        parser.print_help()
        return 2
    cfg = load_saas_config()
    log.configure(cfg.log_json, cfg.log_level)
    if not cfg.user_mail_configured:
        print("not configured: set APPLYFIRST_SMTP_HOST, APPLYFIRST_SMTP_USER and "
              "APPLYFIRST_SMTP_PASSWORD")
        return 1
    sample = db.User(id="test", google_sub="test", email=args.test, display_name=None,
                     plan="free", created_at="")
    try:
        _send(cfg, args.test, *compose(cfg, sample))
    except Exception as exc:  # noqa: BLE001 — report it, whatever it is
        print(f"failed: {_describe(cfg, exc)}")
        return 1
    print(f"sent to {args.test} from {cfg.smtp_user}. Check that inbox and its spam folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
