"""Compose alert emails (subject + plain text + HTML).

Two builders:
- build_job_email: pre-AI alert (raw description + detected screening hints).
- build_tailored_email: full AI package (cover letter + answered questions + token),
  used when a profile is configured. All job-supplied/LLM text is HTML-escaped.
"""

from __future__ import annotations

import html as _html
from typing import Mapping


def _get(job: Mapping, key: str):
    try:
        return job[key]
    except (KeyError, IndexError):
        return None


def _meta(job: Mapping):
    return (
        _get(job, "title") or "(untitled)",
        _get(job, "url") or "",
        _get(job, "employment_type") or "—",
        _get(job, "salary_text") or "—",
        _get(job, "posted_at") or "?",
        _get(job, "matched_keyword") or "—",
    )


def build_job_email(job: Mapping, hints: list[str]) -> tuple[str, str, str]:
    title, url, etype, salary, posted, keyword = _meta(job)
    desc = (_get(job, "raw_description") or "").strip()

    subject = f"🆕 {title} [{etype}] — onlinejobs.ph"
    lines = [
        title, "",
        f"Type: {etype}    Salary: {salary}",
        f"Posted: {posted} UTC    Matched keyword: {keyword}",
        f"Apply: {url}",
    ]
    if hints:
        lines += ["", "📋 Application instructions detected — make sure you answer these:"]
        lines += [f"   • {h}" for h in hints]
    lines += ["", "─" * 30, "JOB DESCRIPTION", "─" * 30,
              desc or "(no description captured)", "", "— Caught by ApplyFirst"]
    text = "\n".join(lines)

    esc = _html.escape
    hints_html = ""
    if hints:
        items = "".join(f"<li>{esc(h)}</li>" for h in hints)
        hints_html = ('<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;'
                      'padding:10px 14px;margin:12px 0"><strong>📋 Application instructions detected'
                      f'</strong><ul style="margin:6px 0 0">{items}</ul></div>')
    body = esc(desc) if desc else "(no description captured)"
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#111">'
        f'<h2 style="margin:0 0 6px">{esc(title)}</h2>'
        f'<p style="color:#555;margin:0 0 10px">{esc(etype)} · {esc(salary)} · posted '
        f'{esc(str(posted))} UTC · matched &ldquo;{esc(keyword)}&rdquo;</p>'
        f'<p style="margin:0 0 12px"><a href="{esc(url)}" style="background:#2563eb;color:#fff;'
        'padding:9px 16px;border-radius:6px;text-decoration:none;display:inline-block">'
        'Apply on onlinejobs.ph →</a></p>'
        f'{hints_html}'
        '<h3 style="margin:16px 0 6px">Job description</h3>'
        '<pre style="white-space:pre-wrap;font-family:inherit;background:#f6f7f9;padding:12px;'
        f'border-radius:8px;margin:0">{body}</pre>'
        '<p style="color:#9ca3af;font-size:12px;margin-top:14px">Caught by ApplyFirst</p>'
        "</div>"
    )
    return subject, text, html


def build_tailored_email(job: Mapping, package, ai_available: bool,
                         pdf_filename: str | None = None) -> tuple[str, str, str]:
    title, url, etype, salary, posted, keyword = _meta(job)

    subject = f"🆕 {title} [{etype}] — onlinejobs.ph"
    lines = [
        title, "",
        f"Type: {etype}    Salary: {salary}",
        f"Posted: {posted} UTC    Matched keyword: {keyword}",
        f"Apply: {url}", "",
    ]
    if not ai_available:
        lines += ["(AI unavailable — answers are blank; edit before sending.)", ""]
    if package.compliance_token:
        lines += [f"⚠ START YOUR REPLY WITH: {package.compliance_token}", ""]
    lines += ["✍️ READY-TO-PASTE COVER LETTER", "─" * 30, package.cover_letter or "—", ""]
    if package.screening_questions:
        lines += ["📋 SCREENING QUESTIONS — DRAFTED ANSWERS", "─" * 30]
        for i, qa in enumerate(package.screening_questions, 1):
            lines += [f"{i}. Q: {qa.question}",
                      f"   A: {qa.drafted_answer or '(answer manually)'}", ""]
    if pdf_filename:
        lines += [f"📎 Tailored resume attached: {pdf_filename}", ""]
    if package.digest:
        lines += ["─" * 30, "WHAT THEY WANT", "─" * 30, package.digest, ""]
    lines += ["— Caught & tailored by ApplyFirst"]
    text = "\n".join(lines)

    esc = _html.escape
    warn = "" if ai_available else ('<p style="color:#b45309">AI unavailable — answers blank; '
                                    "edit before sending.</p>")
    token = ""
    if package.compliance_token:
        token = ('<p style="background:#fee2e2;border:1px solid #fecaca;border-radius:6px;'
                 f'padding:8px 12px"><strong>⚠ Start your reply with:</strong> '
                 f'{esc(package.compliance_token)}</p>')
    qa_html = ""
    if package.screening_questions:
        items = "".join(
            f"<li style='margin-bottom:8px'><strong>Q:</strong> {esc(q.question)}<br>"
            f"<strong>A:</strong> {esc(q.drafted_answer or '(answer manually)')}</li>"
            for q in package.screening_questions
        )
        qa_html = f'<h3 style="margin:16px 0 6px">Screening questions — drafted answers</h3><ol>{items}</ol>'
    pdf_html = f'<p>📎 Tailored resume attached: {esc(pdf_filename)}</p>' if pdf_filename else ""
    digest_html = ""
    if package.digest:
        digest_html = ('<h3 style="margin:16px 0 6px">What they want</h3>'
                       '<p style="white-space:pre-wrap;color:#555;margin:0">'
                       f'{esc(package.digest)}</p>')
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#111">'
        f'<h2 style="margin:0 0 4px">{esc(title)}</h2>'
        f'<p style="color:#555;margin:0 0 8px">{esc(etype)} · {esc(salary)} · posted '
        f'{esc(str(posted))} UTC · matched &ldquo;{esc(keyword)}&rdquo;</p>'
        f'<p><a href="{esc(url)}" style="background:#2563eb;color:#fff;padding:9px 16px;'
        'border-radius:6px;text-decoration:none;display:inline-block">Apply on onlinejobs.ph →</a></p>'
        f'{warn}{token}'
        '<h3 style="margin:16px 0 6px">Ready-to-paste cover letter</h3>'
        '<pre style="white-space:pre-wrap;font-family:inherit;background:#f6f7f9;padding:12px;'
        f'border-radius:8px;margin:0">{esc(package.cover_letter or "—")}</pre>'
        f'{qa_html}{pdf_html}{digest_html}'
        '<p style="color:#9ca3af;font-size:12px;margin-top:14px">Caught &amp; tailored by ApplyFirst</p>'
        "</div>"
    )
    return subject, text, html
