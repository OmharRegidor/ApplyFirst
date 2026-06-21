"""Gmail API send for the M3 worker — httpx + stdlib email, no google-api-python-client.

The worker holds a user's envelope-decrypted gmail.send refresh token (via
``db.get_gmail_refresh_token``) and sends a tailored application FROM the user's Gmail TO
their own inbox. Two hops: refresh-token → access-token, then ``messages.send``.

A revoked/expired refresh token (Google: ``invalid_grant``) or an insufficient-scope
send raises :class:`GmailAuthError` so the worker can mark that user's Gmail disconnected
(``db.clear_gmail_credential``) instead of retrying forever. Transient/operational
failures raise :class:`GmailSendError` (the worker may retry next tick).
"""

from __future__ import annotations

import base64
from email.message import EmailMessage

import httpx

from applyfirst.saas.config import SaaSConfig

TOKEN_URI = "https://oauth2.googleapis.com/token"
SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailSendError(Exception):
    """Transient/operational Gmail send failure — safe for the worker to retry later."""


class GmailAuthError(GmailSendError):
    """The user's gmail.send grant is gone (invalid_grant / insufficient scope).

    Subclasses GmailSendError so a blanket ``except GmailSendError`` still catches it, but
    the worker should branch on this type to DISCONNECT the user rather than retry.
    """


def get_access_token(cfg: SaaSConfig, refresh_token: str) -> str:
    """Exchange a gmail.send refresh token for a short-lived access token.

    Raises GmailAuthError if Google reports ``invalid_grant`` (token revoked/expired) —
    the worker must mark this user's Gmail disconnected. Raises GmailSendError on any
    other failure (network, invalid_client, non-200) — that's our problem, not the user's.
    """
    data = {
        "grant_type": "refresh_token",
        "client_id": cfg.google_client_id or "",
        "client_secret": cfg.google_client_secret or "",
        "refresh_token": refresh_token,
    }
    try:
        resp = httpx.post(TOKEN_URI, data=data, timeout=15)
    except httpx.HTTPError as exc:
        raise GmailSendError(f"token endpoint unreachable: {exc}") from exc

    if resp.status_code == 200:
        token = resp.json().get("access_token")
        if not token:
            raise GmailSendError("token response had no access_token")
        return token

    error = ""
    try:
        error = (resp.json() or {}).get("error", "")
    except ValueError:
        pass
    if resp.status_code == 400 and error == "invalid_grant":
        raise GmailAuthError("refresh token revoked or expired (invalid_grant)")
    raise GmailSendError(f"token refresh failed: {resp.status_code} {error}".strip())


def _build_raw(*, to: str, subject: str, text: str, html: str | None) -> str:
    """RFC 2822 MIME → urlsafe base64 for Gmail's ``raw`` field (send-to-self: From=To)."""
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def send_email(cfg: SaaSConfig, refresh_token: str, *,
               to: str, subject: str, text: str, html: str | None = None) -> str:
    """Send one email FROM/TO the user's own Gmail. Returns the Gmail message id.

    Raises GmailAuthError if the grant is gone (worker → disconnect the user) or
    GmailSendError on transient/operational failures (worker → retry next tick).
    """
    access_token = get_access_token(cfg, refresh_token)
    raw = _build_raw(to=to, subject=subject, text=text, html=html)
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = httpx.post(SEND_URI, json={"raw": raw}, headers=headers, timeout=30)
    except httpx.HTTPError as exc:
        raise GmailSendError(f"gmail send unreachable: {exc}") from exc

    if resp.status_code == 200:
        return resp.json().get("id", "")
    if resp.status_code == 403:
        raise GmailAuthError(f"gmail send forbidden (insufficient scope): {resp.text[:200]}")
    raise GmailSendError(f"gmail send failed: {resp.status_code} {resp.text[:200]}")
