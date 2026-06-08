"""Tests for alert-email composition."""

from __future__ import annotations

from applyfirst.notify.compose import build_job_email


def _job(**overrides):
    job = {
        "title": "VA Role",
        "url": "https://www.onlinejobs.ph/jobseekers/job/x-1",
        "employment_type": "Full Time",
        "salary_text": "$500",
        "posted_at": "2026-06-08 10:00:00",
        "matched_keyword": "virtual assistant",
        "raw_description": "Do stuff.\nTO APPLY\n1. What is your favorite hobby?",
    }
    job.update(overrides)
    return job


def test_build_email_includes_key_fields():
    subject, text, html = build_job_email(_job(), hints=["1. What is your favorite hobby?"])
    assert "VA Role" in subject
    assert "https://www.onlinejobs.ph/jobseekers/job/x-1" in text
    assert "favorite hobby" in text
    assert "Application instructions detected" in text
    assert html and "VA Role" in html


def test_build_email_escapes_html_in_untrusted_fields():
    subject, text, html = build_job_email(
        _job(title="A & B <script>alert(1)</script>"), hints=[]
    )
    assert "<script>" not in html  # scraped/LLM text must be escaped in HTML
    assert "&lt;script&gt;" in html
