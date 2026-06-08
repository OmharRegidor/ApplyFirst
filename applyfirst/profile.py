"""The candidate profile — loaded once from profile.yaml.

This is the trusted source of truth the AI tailors from. Validated with Pydantic
so a malformed YAML fails loudly with a clear error.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Experience(BaseModel):
    role_id: str = ""
    title: str = ""
    company: str = ""
    start: str = ""
    end: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    qualification: str = ""
    institution: str = ""
    year: str = ""


class Profile(BaseModel):
    full_name: str = ""
    contact_email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)
    target_summary: str = ""
    professional_summary: str = ""
    voice_tone: str = "warm, concise, professional"
    base_pitch: str = ""
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)


def load_profile(path: str | Path) -> Profile:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Profile not found at {p}. Copy profile.example.yaml to {p} and fill it in."
        )
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Profile.model_validate(data)
