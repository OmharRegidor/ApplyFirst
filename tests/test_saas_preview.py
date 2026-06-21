"""M2 — onboarding preview builds from the 4 fields with no API key (rules-fallback)."""

from __future__ import annotations

from applyfirst.saas import preview


def test_preview_uses_standard_message_and_subject():
    pv = preview.build_preview(
        full_name="Omhar", job_type="Virtual Assistant",
        standard_subject="VA - Omhar", standard_message="Hi, I am Omhar.")
    assert "Hi, I am Omhar." in pv["cover_letter"]
    assert pv["subject"] == "VA - Omhar"
    assert isinstance(pv["screening_questions"], list)
    assert pv["sample_job"]


def test_preview_handles_empty_subject():
    pv = preview.build_preview(
        full_name="A", job_type="VA", standard_subject="", standard_message="Hello there")
    assert pv["cover_letter"].strip() == "Hello there"   # fallback uses the message verbatim
