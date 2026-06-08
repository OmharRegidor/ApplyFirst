"""Tests for the tailoring engine (offline — no real LLM key needed)."""

from __future__ import annotations

from applyfirst.profile import Experience, Profile
from applyfirst.tailor.engine import TailoringEngine, parse_package
from applyfirst.tailor.prompt import build_system_prompt, build_user_prompt

SAMPLE_PROFILE = Profile(
    full_name="Juan Dela Cruz",
    professional_summary="VA with customer-service experience.",
    base_pitch="Hi, I'd love to help.",
    voice_tone="warm",
    skills=["Customer service", "Shopify"],
    experience=[Experience(role_id="cs", title="CSR", company="Comfit", bullets=["Handled tickets."])],
)

JOB = (
    "We need a VA.\nTO APPLY\nPlease reply with:\n"
    "1. Your experience\n"
    "2. To show you read this, what is your favorite hobby?"
)


class FakeProvider:
    name = "gemini"

    def __init__(self, raw: str) -> None:
        self.raw = raw

    def generate(self, system: str, user: str) -> str:
        return self.raw


class BoomProvider:
    name = "gemini"

    def generate(self, system: str, user: str) -> str:
        raise RuntimeError("rate limited")


def test_parse_package_tolerates_fences_and_prose():
    raw = ('Sure, here is the JSON:\n```json\n'
           '{"digest":"d","cover_letter":"c",'
           '"screening_questions":[{"question":"q","drafted_answer":"a"}]}\n```')
    pkg = parse_package(raw)
    assert pkg.digest == "d"
    assert pkg.screening_questions[0].drafted_answer == "a"


def test_engine_happy_path_with_fake_provider():
    good = ('{"digest":"role","compliance_token":null,"cover_letter":"Hello",'
            '"screening_questions":[{"question":"favorite hobby?","drafted_answer":"Reading"}],'
            '"resume_overrides":{"summary":"s","emphasize_skills":["Shopify"],"tailored_bullets":[]}}')
    res = TailoringEngine(provider=FakeProvider(good)).build(JOB, SAMPLE_PROFILE)
    assert res.ai_available is True
    assert res.provider == "gemini"
    assert res.package.cover_letter == "Hello"
    assert any("hobby" in q.question.lower() for q in res.package.screening_questions)


def test_engine_falls_back_when_provider_fails():
    res = TailoringEngine(provider=BoomProvider(), retries=2).build(JOB, SAMPLE_PROFILE)
    assert res.ai_available is False
    assert res.provider == "rules-fallback"
    assert res.package.cover_letter == "Hi, I'd love to help."
    assert any("hobby" in q.question.lower() for q in res.package.screening_questions)


def test_prompts_have_trust_separation_and_rules():
    system = build_system_prompt("warm")
    assert "TRUTHFUL" in system.upper()
    assert "UNTRUSTED" in system.upper()
    user = build_user_prompt(SAMPLE_PROFILE, JOB)
    assert "untrusted" in user.lower()
    assert "Juan Dela Cruz" in user
    assert "favorite hobby" in user
