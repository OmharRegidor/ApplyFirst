"""TailoringEngine: job description + profile -> validated application package.

Calls the LLM (with retries), validates the JSON against the contract, and falls
back to a rules-based package if the LLM is unavailable or keeps returning junk —
so the pipeline always produces *something* and never crashes on a bad response.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from applyfirst.profile import Profile
from applyfirst.screening import detect_screening_hints
from applyfirst.tailor.contract import ResumeOverrides, ScreeningQA, TailoredPackage
from applyfirst.tailor.prompt import build_system_prompt, build_user_prompt

_NUMBERED = re.compile(r"^\d+[\.\)]")


def parse_package(raw: str) -> TailoredPackage:
    """Parse an LLM response into a TailoredPackage, tolerating fences/prose."""
    text = raw.strip()
    if text.startswith("```"):
        # drop the opening fence line and any trailing fence
        text = text.split("\n", 1)[1] if "\n" in text else text
        if "```" in text:
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    obj = json.loads(text)
    return TailoredPackage.model_validate(obj)


@dataclass(slots=True)
class TailorResult:
    package: TailoredPackage
    provider: str       # "gemini" | "rules-fallback"
    ai_available: bool


class TailoringEngine:
    def __init__(self, provider=None, retries: int = 2) -> None:
        self.provider = provider
        self.retries = max(1, retries)

    def build(self, job_description: str, profile: Profile) -> TailorResult:
        if self.provider is not None:
            system = build_system_prompt(profile.voice_tone)
            user = build_user_prompt(profile, job_description)
            for _ in range(self.retries):
                try:
                    raw = self.provider.generate(system, user)
                    package = parse_package(raw)
                    return TailorResult(package, getattr(self.provider, "name", "llm"), True)
                except Exception:
                    continue
        return TailorResult(self._fallback(job_description, profile), "rules-fallback", False)

    def _fallback(self, job_description: str, profile: Profile) -> TailoredPackage:
        hints = detect_screening_hints(job_description)
        questions = [
            ScreeningQA(question=h)
            for h in hints
            if h.endswith("?") or _NUMBERED.match(h)
        ]
        digest = " ".join(job_description.split())[:240]
        return TailoredPackage(
            digest=digest,
            screening_questions=questions,
            compliance_token=None,
            cover_letter=profile.base_pitch.strip(),
            resume_overrides=ResumeOverrides(emphasize_skills=profile.skills[:8]),
        )
