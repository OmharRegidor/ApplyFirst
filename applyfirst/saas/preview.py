"""Onboarding preview — show a sample ready-to-paste application from the 4 fields.

Reuses the existing tailoring engine in **rules-fallback** mode (``provider=None``), so
the preview is deterministic, free, and needs no Gemini key. The live AI tailoring is
wired in M3; here we show the user's own Standard Message against a fixture job so they
see the shape of what lands in their inbox.
"""

from __future__ import annotations

from applyfirst.profile import Profile
from applyfirst.tailor.engine import TailoringEngine

# A representative onlinejobs.ph-style post, incl. a buried "to apply" instruction.
SAMPLE_JOB = (
    "Virtual Assistant for a growing e-commerce store.\n\n"
    "We need help with customer support, order management, and light admin work. "
    "Must have good written English and be reliable.\n\n"
    "TO APPLY: tell us briefly why you're a good fit and what tools you've used."
)


def to_profile(*, full_name: str, job_type: str,
               standard_subject: str, standard_message: str) -> Profile:
    """Map the SaaS 4-field profile → the applyfirst.profile.Profile the tailor expects.

    Shared by the onboarding preview and the M3 worker so both tailor from the SAME shape.
    """
    return Profile(
        full_name=full_name,
        target_summary=job_type,
        professional_summary=job_type,
        base_pitch=standard_message,
        subject_library={"general": [standard_subject]} if standard_subject else {},
    )


def build_preview(*, full_name: str, job_type: str,
                  standard_subject: str, standard_message: str) -> dict:
    """Return a preview dict: {subject, cover_letter, screening_questions, sample_job}."""
    profile = to_profile(full_name=full_name, job_type=job_type,
                         standard_subject=standard_subject, standard_message=standard_message)
    package = TailoringEngine(provider=None).build(SAMPLE_JOB, profile).package
    return {
        "subject": package.application_subject or standard_subject,
        "cover_letter": package.cover_letter or standard_message,
        "screening_questions": [q.question for q in package.screening_questions],
        "sample_job": SAMPLE_JOB,
    }
