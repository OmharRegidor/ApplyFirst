"""The V1 Apply link carries the Subject and Message after ``#agad=`` for the Chrome
extension. Opt-in only: the SaaS email (default call) stays byte-for-byte the same."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from pathlib import Path

import pytest

from applyfirst import pipeline
from applyfirst.notify.compose import build_apply_link, build_tailored_email
from applyfirst.tailor.contract import ScreeningQA, TailoredPackage
from applyfirst.tailor.engine import TailoringEngine
from _saas_client import RecordingProvider
from test_compose import _job
from test_tailor_prompt import _v1_profile

URL = "https://www.onlinejobs.ph/jobseekers/job/Senior-Dev-1234567"
VECTORS = Path(__file__).resolve().parent.parent / "extension" / "test" / "vectors.json"
_HREF_RE = re.compile(r'<a href="([^"]*)"[^>]*>Apply on onlinejobs\.ph</a>')

# sha256 of subject + "\x00" + text + "\x00" + html for the input below, captured at
# HEAD 21308d1 before compose.py gained fill_link. It must never change.
_SAAS_GUARD_SHA256 = "3745b7eda53aacd9d4ffdac90c4335ad9118db59d4c1a290804e214d16c50024"


def _decode(link: str) -> dict:
    payload = link.split("#agad=", 1)[1]
    assert re.fullmatch(r"[A-Za-z0-9_-]+", payload)            # urlsafe, no "=" padding
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _pkg(**overrides) -> TailoredPackage:
    fields = dict(digest="d", application_subject="VA – Maria", compliance_token="",
                  cover_letter="Hi! I'm Maria.", screening_questions=[])
    fields.update(overrides)
    return TailoredPackage(**fields)


# --- SaaS byte-identical guard ----------------------------------------------------------

def test_default_call_is_byte_identical_to_head():
    job = {"title": "VA Role", "url": "https://www.onlinejobs.ph/jobseekers/job/x-1",
           "employment_type": "Full Time", "salary_text": "$500",
           "posted_at": "2026-06-08 10:00:00", "matched_keyword": "virtual assistant",
           "raw_description": "Do stuff."}
    pkg = TailoredPackage(
        digest="They want a VA.", application_subject="VA Application – Maria & Co",
        compliance_token="PINEAPPLE",
        cover_letter="Hi! I'm Maria.\n<b>5 years</b> & \"quotes\" #1 😀",
        screening_questions=[ScreeningQA(question="Hobby?", drafted_answer="Reading")])
    s, t, h = build_tailored_email(job, pkg, ai_available=True)
    digest = hashlib.sha256((s + "\x00" + t + "\x00" + h).encode("utf-8")).hexdigest()
    assert digest == _SAAS_GUARD_SHA256


def test_fill_link_is_keyword_only():
    with pytest.raises(TypeError):
        build_tailored_email(_job(), _pkg(), True, None, False, True)


# --- build_apply_link -------------------------------------------------------------------

@pytest.mark.parametrize("subject,message", [
    ("Dev 😀 – Señora", "Salamat po! 🙏🏽\nNiño"),
    ("A & B # C", "<script>alert(1)</script> & \"quotes\" 'single' #hash\nline two\r\n"),
    ("", "only a message"),
    ("only a subject", ""),
])
def test_round_trip(subject, message):
    link = build_apply_link(URL, subject, message)
    assert link.startswith(URL + "#agad=")
    assert _decode(link) == {"v": 1, "j": "1234567", "s": subject, "m": message}


def test_none_texts_count_as_empty():
    assert _decode(build_apply_link(URL, None, "msg")) == {"v": 1, "j": "1234567",
                                                            "s": "", "m": "msg"}
    assert build_apply_link(URL, None, None) == URL


def test_trailing_slash_url_still_reads_the_job_id():
    assert _decode(build_apply_link(URL + "/", "s", "m"))["j"] == "1234567"


@pytest.mark.parametrize("url,subject,message", [
    (URL, "", ""),                                              # nothing to carry
    (URL, "x" * 201, "m"),                                      # subject over cap
    (URL, "s", "x" * 5001),                                     # message over cap
    (URL, "😀" * 101, "m"),                                     # 202 UTF-16 units
    ("https://www.onlinejobs.ph/login", "s", "m"),              # no job id
    ("", "s", "m"),                                             # no URL at all
    ("https://www.onlinejobs.ph/jobseekers/job/x-1234567890123", "s", "m"),  # 13 digits
    (URL, "s", "bad \ud800 surrogate"),                         # not encodable as UTF-8
], ids=["empty", "subject-cap", "message-cap", "utf16-cap", "no-job-id", "no-url",
        "long-id", "lone-surrogate"])
def test_falls_back_to_the_plain_url(url, subject, message):
    assert build_apply_link(url, subject, message) == url


def test_caps_are_inclusive():
    link = build_apply_link(URL, "x" * 200, "y" * 5000)
    assert _decode(link)["m"] == "y" * 5000
    assert _decode(build_apply_link(URL, "😀" * 100, "m"))["s"] == "😀" * 100


def test_an_old_fragment_is_replaced_not_doubled():
    link = build_apply_link(URL + "#x", "s", "m")
    assert link.startswith(URL + "#agad=")
    assert link.count("#") == 1


def test_python_matches_the_extension_vectors():
    if not VECTORS.exists():
        pytest.skip(f"{VECTORS} not written yet (owned by the extension builder)")
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert vectors, "vectors.json is empty"
    for vec in vectors:
        url = vec.get("url") or f"https://www.onlinejobs.ph/jobseekers/job/x-{vec['j']}"
        link = build_apply_link(url, vec["s"], vec["m"])
        assert link.split("#agad=", 1)[1] == vec["fragment"], vec.get("name")
        if "link" in vec:
            assert link == vec["link"], vec.get("name")


# --- build_tailored_email(fill_link=True) ------------------------------------------------

def test_fill_link_changes_only_the_html_href():
    pkg = _pkg(application_subject="A & B", cover_letter="Hi <b>there</b> & #1\nBye")
    job = _job(url=URL)
    s0, t0, h0 = build_tailored_email(job, pkg, True)
    s1, t1, h1 = build_tailored_email(job, pkg, True, fill_link=True)
    assert (s1, t1) == (s0, t0)
    assert f"Apply: {URL}\n" in t1
    assert "SUBJECT TO PASTE" in t1 and "MESSAGE" in t1
    href = _HREF_RE.search(h1).group(1)
    link = build_apply_link(URL, pkg.application_subject, pkg.cover_letter)
    assert href == html.escape(link)
    assert "#agad=" in href
    assert h1.replace(href, html.escape(URL), 1) == h0


def test_fill_link_falls_back_to_plain_url_when_nothing_to_carry():
    _, _, h = build_tailored_email(_job(url=URL), _pkg(application_subject="", cover_letter=""),
                                   True, fill_link=True)
    assert _HREF_RE.search(h).group(1) == html.escape(URL)



@pytest.mark.parametrize("subject,message", [("A & B", "Hi #1"), ("", "")],
                         ids=["filled", "empty"])
def test_fill_link_when_ai_is_down(subject, message):
    pkg = _pkg(application_subject=subject, cover_letter=message)
    job = _job(url=URL)
    s0, t0, h0 = build_tailored_email(job, pkg, False)
    s1, t1, h1 = build_tailored_email(job, pkg, False, fill_link=True)
    assert (s1, t1) == (s0, t0)
    assert "AI unavailable" in h1
    href = _HREF_RE.search(h1).group(1)
    if subject or message:
        assert href == html.escape(build_apply_link(URL, subject, message))
        assert "#agad=" in href
    else:
        assert href == html.escape(URL)
    assert h1.replace(href, html.escape(URL), 1) == h0

# --- pipeline wiring ---------------------------------------------------------------------

def test_v1_pipeline_email_carries_the_filled_link():
    reply = json.dumps({"digest": "d", "application_subject": "Dev – Juan",
                        "cover_letter": "Hi! I'm Juan.", "screening_questions": []})

    class NullStore:
        def save_tailored(self, job_id, res):
            pass

    row = {"id": 1, "title": "Dev", "url": URL, "posted_at": None,
           "raw_description": "Need a dev."}
    _, text, h, _ = pipeline._compose_for(NullStore(), row,
                                          TailoringEngine(provider=RecordingProvider(reply)),
                                          _v1_profile(), verbose=False)
    href = html.unescape(_HREF_RE.search(h).group(1))
    assert href.startswith(URL + "#agad=")
    assert _decode(href) == {"v": 1, "j": "1234567", "s": "Dev – Juan", "m": "Hi! I'm Juan."}
    assert f"Apply: {URL}\n" in text
