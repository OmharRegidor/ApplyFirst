"""Tests for the resume PDF renderer."""

from __future__ import annotations

import pytest

from applyfirst.pdf import render_resume_pdf
from applyfirst.profile import Education, Experience, Profile
from applyfirst.tailor.contract import ResumeOverrides, TailoredBullets

# Guard against the fpdf2 wrapmode infinite-loop ever silently re-hanging the
# suite: any render taking > 5s fails fast instead of stalling the whole run.
pytestmark = pytest.mark.timeout(5)


def _profile():
    return Profile(
        full_name="Juan Dela Cruz",
        contact_email="juan@example.com",
        professional_summary="VA with customer-service experience.",
        skills=["Customer service", "Shopify"],
        tools=["Gorgias"],
        experience=[Experience(role_id="cs", title="CSR", company="Comfit",
                               start="2023", end="now", bullets=["Handled tickets."])],
        education=[Education(qualification="BS IT", institution="Uni", year="2021")],
    )


def test_render_resume_pdf_returns_pdf_bytes():
    data = render_resume_pdf(_profile())
    assert isinstance(data, (bytes, bytearray))
    assert bytes(data[:5]) == b"%PDF-"
    assert len(data) > 800


def test_render_with_overrides_does_not_crash():
    overrides = ResumeOverrides(
        summary="Tailored summary for this job.",
        emphasize_skills=["Shopify"],
        tailored_bullets=[TailoredBullets(role_id="cs", bullets=["Tailored bullet for the role."])],
    )
    data = render_resume_pdf(_profile(), overrides)
    assert bytes(data[:5]) == b"%PDF-"


def test_render_handles_unicode_safely():
    prof = _profile()
    prof.full_name = "Renée — Café ☕ Niño"  # smart dashes / accents / emoji
    data = render_resume_pdf(prof)
    assert bytes(data[:5]) == b"%PDF-"
