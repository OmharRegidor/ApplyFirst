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
from applyfirst.tailor.prompt import RESUME_ON_REQUEST, build_system_prompt, build_user_prompt

_NUMBERED = re.compile(r"^\d+[\.\)]")
# The post asks for a resume or CV (used only when no resume file is sent).
_ASKS_FOR_RESUME = re.compile(r"\b(r[eé]sum[eé]s?|cvs?|curriculum vitae)\b", re.IGNORECASE)

# Keyword → subject_library category, used by the no-AI fallback to pick a subject.
_CATEGORY_HINTS = [
    ("react_native_mobile", ("react native", "mobile", "android", "ios", "app store")),
    ("ai_agentic_automation", ("ai ", "agent", "automation", "llm", "gpt", "claude", "chatbot")),
    ("backend_api", ("backend", "back-end", "api", "node", "express", "postgres", "database")),
    ("ecommerce_msme", ("ecommerce", "e-commerce", "shopify", "woocommerce", "pos", "inventory", "crm")),
    ("frontend_react", ("frontend", "front-end", "react", "ui", "tailwind", "next.js", "nextjs")),
    ("technical_va", ("virtual assistant", "va ", "admin", "operations")),
]


def _pick_subject_fallback(job_description: str, profile: Profile) -> str:
    """No-AI subject pick: keyword-match the job to a subject_library category."""
    library = getattr(profile, "subject_library", None) or {}
    if not library:
        return ""
    desc = (job_description or "").lower()
    for category, needles in _CATEGORY_HINTS:
        if category in library and library[category] and any(n in desc for n in needles):
            return library[category][0]
    # default: first subject in the full-stack/software category, else the first of any.
    if library.get("fullstack_software"):
        return library["fullstack_software"][0]
    for subjects in library.values():
        if subjects:
            return subjects[0]
    return ""


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

    def build(self, job_description: str, profile: Profile, *,
              resume_attached: bool = True) -> TailorResult:
        """Tailor one job for one profile.

        ``resume_attached`` says whether a resume file really goes out with this application.
        The default (True) is the V1 pipeline/CLI, which render and attach a PDF. Pass False
        whenever no resume file is sent (every SaaS call site does, as a literal): the letter
        then never claims a resume is attached and offers to send it on request instead.
        """
        if self.provider is not None:
            system = build_system_prompt(profile.voice_tone, resume_attached=resume_attached)
            user = build_user_prompt(profile, job_description)
            for _ in range(self.retries):
                try:
                    raw = self.provider.generate(system, user)
                    package = parse_package(raw)
                    return TailorResult(package, getattr(self.provider, "name", "llm"), True)
                except Exception:
                    continue
        package = self._fallback(job_description, profile, resume_attached=resume_attached)
        return TailorResult(package, "rules-fallback", False)

    def _fallback(self, job_description: str, profile: Profile, *,
                  resume_attached: bool) -> TailoredPackage:
        hints = detect_screening_hints(job_description)
        questions = [
            ScreeningQA(question=h)
            for h in hints
            if h.endswith("?") or _NUMBERED.match(h)
        ]
        digest = " ".join(job_description.split())[:240]
        return TailoredPackage(
            digest=digest,
            application_subject=_pick_subject_fallback(job_description, profile),
            screening_questions=questions,
            compliance_token=None,
            cover_letter=_fallback_letter(job_description, profile, resume_attached),
            resume_overrides=ResumeOverrides(emphasize_skills=profile.skills[:8]),
        )


def _fallback_letter(job_description: str, profile: Profile, resume_attached: bool) -> str:
    """The candidate's own message, verbatim. With no resume file going out and a post that
    asks for one, it gains the same on-request sentence the AI prompt asks for (never a claim
    that a resume is attached). The V1 default (a PDF is attached) is unchanged."""
    letter = profile.base_pitch.strip()
    if (letter and not resume_attached and _ASKS_FOR_RESUME.search(job_description or "")
            and RESUME_ON_REQUEST.lower() not in letter.lower()):
        letter = f"{letter}\n\n{RESUME_ON_REQUEST}"
    return letter
