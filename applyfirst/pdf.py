"""Render a clean, tailored resume PDF (pure-Python via fpdf2 — no system deps).

We own the template, so we generate from structured profile data + the AI's
resume_overrides rather than editing a file. Core fonts (latin-1) keep it
dependency-free; text is sanitized so unusual characters never crash rendering,
and CHAR wrap mode keeps long unbreakable tokens (URLs) from overflowing.
"""

from __future__ import annotations

from fpdf import FPDF

from applyfirst.profile import Profile
from applyfirst.tailor.contract import ResumeOverrides

_REPL = {
    "–": "-", "—": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "•": "-", "…": "...", " ": " ",
}


def _san(text: str) -> str:
    if not text:
        return ""
    for k, v in _REPL.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def _mc(pdf: FPDF, height: float, text: str) -> None:
    """multi_cell bounded to the page's usable width so long URLs/tokens wrap
    instead of overflowing. Uses an explicit width (``pdf.epw``) with default
    WORD wrap: fpdf2 2.8.7 infinite-loops on ``multi_cell(0, …, wrapmode="CHAR")``
    (line_break.py get_line), and a bounded cell still hard-breaks unbreakable
    tokens at the edge."""
    pdf.multi_cell(pdf.epw, height, _san(text))


def _section(pdf: FPDF, title: str) -> None:
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(37, 99, 235)
    _mc(pdf, 6, title)
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(210, 210, 210)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(1)


def render_resume_pdf(profile: Profile, overrides: ResumeOverrides | None = None) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    _mc(pdf, 9, profile.full_name or "Resume")

    contact_bits = [profile.contact_email, profile.phone, profile.location] + list(profile.links)
    contact = "  |  ".join(b for b in contact_bits if b)
    if contact:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(90, 90, 90)
        _mc(pdf, 5, contact)
        pdf.set_text_color(0, 0, 0)

    summary = overrides.summary if (overrides and overrides.summary) else profile.professional_summary
    if summary:
        _section(pdf, "SUMMARY")
        pdf.set_font("Helvetica", "", 10)
        _mc(pdf, 5, summary)

    skills = list(profile.skills)
    if overrides and overrides.emphasize_skills:
        emphasized = list(overrides.emphasize_skills)
        skills = emphasized + [s for s in skills if s not in emphasized]
    if skills:
        _section(pdf, "SKILLS")
        pdf.set_font("Helvetica", "", 10)
        _mc(pdf, 5, ", ".join(skills))
    if profile.tools:
        _section(pdf, "TOOLS")
        pdf.set_font("Helvetica", "", 10)
        _mc(pdf, 5, ", ".join(profile.tools))

    override_map = {}
    if overrides:
        override_map = {tb.role_id: tb.bullets for tb in overrides.tailored_bullets if tb.bullets}
    if profile.experience:
        _section(pdf, "EXPERIENCE")
        for exp in profile.experience:
            pdf.set_font("Helvetica", "B", 11)
            header = exp.title + (f" - {exp.company}" if exp.company else "")
            _mc(pdf, 6, header or exp.company)
            if exp.start or exp.end:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(90, 90, 90)
                _mc(pdf, 5, f"{exp.start} - {exp.end}".strip(" -"))
                pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 10)
            for bullet in (override_map.get(exp.role_id) or exp.bullets):
                _mc(pdf, 5, f"- {bullet}")
            pdf.ln(1)

    if profile.education:
        _section(pdf, "EDUCATION")
        pdf.set_font("Helvetica", "", 10)
        for ed in profile.education:
            line = " - ".join(b for b in [ed.qualification, ed.institution, ed.year] if b)
            if line:
                _mc(pdf, 5, line)

    if profile.certifications:
        _section(pdf, "CERTIFICATIONS")
        pdf.set_font("Helvetica", "", 10)
        _mc(pdf, 5, ", ".join(profile.certifications))
    if profile.languages:
        _section(pdf, "LANGUAGES")
        pdf.set_font("Helvetica", "", 10)
        _mc(pdf, 5, ", ".join(profile.languages))

    return bytes(pdf.output())
