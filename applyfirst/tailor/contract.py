"""The strict JSON contract the LLM must return (validated with Pydantic).

Extra/unknown fields are ignored; missing fields get safe defaults — so a slightly
sloppy model response still validates instead of crashing the pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScreeningQA(BaseModel):
    question: str
    drafted_answer: str = ""


class TailoredBullets(BaseModel):
    role_id: str = ""
    bullets: list[str] = Field(default_factory=list)


class ResumeOverrides(BaseModel):
    summary: str = ""
    emphasize_skills: list[str] = Field(default_factory=list)
    tailored_bullets: list[TailoredBullets] = Field(default_factory=list)


class TailoredPackage(BaseModel):
    digest: str = ""
    screening_questions: list[ScreeningQA] = Field(default_factory=list)
    compliance_token: str | None = None
    cover_letter: str = ""
    resume_overrides: ResumeOverrides = Field(default_factory=ResumeOverrides)
