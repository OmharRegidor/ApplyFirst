"""M3 — Gmail API send: token refresh + send (mocked httpx), typed error branches."""

from __future__ import annotations

import base64
import email

import pytest

from applyfirst.saas import gmail_send
from applyfirst.saas.gmail_send import GmailAuthError, GmailSendError


class FakeResp:
    def __init__(self, status, *, json_body=None, text=""):
        self.status_code = status
        self._json = json_body
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _patch(monkeypatch, token_resp, send_resp=None, sink=None):
    def fake_post(url, **kw):
        if url == gmail_send.TOKEN_URI:
            return token_resp
        if sink is not None:
            sink.update(kw)
        return send_resp
    monkeypatch.setattr(gmail_send.httpx, "post", fake_post)


def test_send_happy_path_builds_valid_mime(saas_cfg, monkeypatch):
    sink = {}
    _patch(monkeypatch, FakeResp(200, json_body={"access_token": "ya29.x"}),
           FakeResp(200, json_body={"id": "msg123"}), sink)
    mid = gmail_send.send_email(saas_cfg, "rt", to="u@gmail.com",
                                subject="Hi", text="body", html="<p>body</p>")
    assert mid == "msg123"
    msg = email.message_from_bytes(base64.urlsafe_b64decode(sink["json"]["raw"]))
    assert msg["Subject"] == "Hi"
    assert msg["From"] == "u@gmail.com" == msg["To"]          # send-to-self
    assert msg.get_content_type() == "multipart/alternative"
    assert sink["headers"]["Authorization"] == "Bearer ya29.x"


def test_plain_only_when_no_html(saas_cfg, monkeypatch):
    sink = {}
    _patch(monkeypatch, FakeResp(200, json_body={"access_token": "x"}),
           FakeResp(200, json_body={"id": "m"}), sink)
    gmail_send.send_email(saas_cfg, "rt", to="u@x", subject="s", text="t")
    msg = email.message_from_bytes(base64.urlsafe_b64decode(sink["json"]["raw"]))
    assert msg.get_content_type() == "text/plain"


def test_revoked_token_raises_auth_error(saas_cfg, monkeypatch):
    _patch(monkeypatch, FakeResp(400, json_body={"error": "invalid_grant"}))
    with pytest.raises(GmailAuthError):
        gmail_send.send_email(saas_cfg, "rt", to="u@x", subject="s", text="t")


def test_invalid_client_is_generic_not_auth(saas_cfg, monkeypatch):
    # Our config bug must NOT disconnect the user.
    _patch(monkeypatch, FakeResp(400, json_body={"error": "invalid_client"}))
    with pytest.raises(GmailSendError) as ei:
        gmail_send.get_access_token(saas_cfg, "rt")
    assert not isinstance(ei.value, GmailAuthError)


def test_token_5xx_is_generic(saas_cfg, monkeypatch):
    _patch(monkeypatch, FakeResp(500, json_body={"error": "server_error"}))
    with pytest.raises(GmailSendError) as ei:
        gmail_send.get_access_token(saas_cfg, "rt")
    assert not isinstance(ei.value, GmailAuthError)


def test_send_403_insufficient_scope_is_auth_error(saas_cfg, monkeypatch):
    _patch(monkeypatch, FakeResp(200, json_body={"access_token": "x"}),
           FakeResp(403, text='{"error":{"message":"insufficient scopes"}}'))
    with pytest.raises(GmailAuthError):
        gmail_send.send_email(saas_cfg, "rt", to="u@x", subject="s", text="t")


def test_send_429_is_generic_retryable(saas_cfg, monkeypatch):
    _patch(monkeypatch, FakeResp(200, json_body={"access_token": "x"}),
           FakeResp(429, text="rate limited"))
    with pytest.raises(GmailSendError) as ei:
        gmail_send.send_email(saas_cfg, "rt", to="u@x", subject="s", text="t")
    assert not isinstance(ei.value, GmailAuthError)


def test_200_without_access_token_is_error(saas_cfg, monkeypatch):
    _patch(monkeypatch, FakeResp(200, json_body={"expires_in": 3599}))  # no access_token
    with pytest.raises(GmailSendError):
        gmail_send.get_access_token(saas_cfg, "rt")


def test_network_error_is_generic_not_auth(saas_cfg, monkeypatch):
    import httpx

    def raises(url, **kw):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(gmail_send.httpx, "post", raises)
    with pytest.raises(GmailSendError) as ei:
        gmail_send.get_access_token(saas_cfg, "rt")
    assert not isinstance(ei.value, GmailAuthError)
