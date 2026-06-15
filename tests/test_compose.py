"""Tests for alert-email composition (pre-AI and AI-tailored)."""

from __future__ import annotations

from applyfirst.notify.compose import build_job_email, build_tailored_email
from applyfirst.tailor.contract import ScreeningQA, TailoredPackage


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


def test_build_job_email_includes_key_fields():
    subject, text, html = build_job_email(_job(), hints=["1. What is your favorite hobby?"])
    assert "VA Role" in subject
    assert "https://www.onlinejobs.ph/jobseekers/job/x-1" in text
    assert "favorite hobby" in text
    assert "Application instructions detected" in text
    assert html and "VA Role" in html


def test_build_job_email_escapes_html_in_untrusted_fields():
    _, _, html = build_job_email(_job(title="A & B <script>alert(1)</script>"), hints=[])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_build_tailored_email_has_letter_answers_token_and_pdf():
    pkg = TailoredPackage(
        digest="They want a VA.",
        cover_letter="banana — Dear hiring manager, I'd love to help.",
        compliance_token="banana",
        screening_questions=[ScreeningQA(question="favorite hobby?", drafted_answer="Reading")],
    )
    subject, text, html = build_tailored_email(_job(), pkg, ai_available=True,
                                               pdf_filename="Juan_resume.pdf")
    assert "VA Role" in subject
    assert "banana" in text and "banana" in html       # compliance token surfaced
    assert "Dear hiring manager" in text                # cover letter
    assert "Reading" in text                            # drafted answer
    assert "Juan_resume.pdf" in text                    # attachment noted
    assert "They want a VA." in text and "They want a VA." in html  # digest in BOTH parts


def test_build_tailored_email_includes_application_subject():
    pkg = TailoredPackage(
        application_subject="AI Automation Engineer | Multi-Agent Pipelines – Omhar Regidor",
        cover_letter="Hi, I'm Omhar.",
    )
    _, text, html = build_tailored_email(_job(), pkg, ai_available=True, pdf_filename="x.pdf")
    assert "SUBJECT TO PASTE" in text
    assert "AI Automation Engineer" in text
    assert "Subject to paste" in html and "AI Automation Engineer" in html


def test_build_tailored_email_flags_unavailable_ai():
    pkg = TailoredPackage(cover_letter="", screening_questions=[ScreeningQA(question="q?")])
    _, text, _ = build_tailored_email(_job(), pkg, ai_available=False)
    assert "AI unavailable" in text
    assert "answer manually" in text


def test_build_tailored_email_notes_pdf_failure():
    pkg = TailoredPackage(cover_letter="Hello.")
    _, text, html = build_tailored_email(_job(), pkg, ai_available=True,
                                         pdf_filename=None, pdf_failed=True)
    assert "Resume PDF could not be generated" in text
    assert "Resume PDF could not be generated" in html


def test_build_tailored_email_no_pdf_note_when_attached():
    pkg = TailoredPackage(cover_letter="Hello.")
    _, text, _ = build_tailored_email(_job(), pkg, ai_available=True,
                                      pdf_filename="Juan_resume.pdf", pdf_failed=False)
    assert "could not be generated" not in text
    assert "Juan_resume.pdf" in text
