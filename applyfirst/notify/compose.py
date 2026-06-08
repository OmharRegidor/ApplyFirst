"""Compose the alert email (subject + plain text + HTML) for a caught job.

Pure function — takes a job mapping (a sqlite Row or a dict) and the detected
screening hints, returns (subject, text, html). All job-supplied text is
HTML-escaped in the HTML part (scraped content is untrusted).
"""

from __future__ import annotations

import html as _html
from typing import Mapping


def _get(job: Mapping, key: str):
    try:
        return job[key]
    except (KeyError, IndexError):
        return None


def build_job_email(job: Mapping, hints: list[str]) -> tuple[str, str, str]:
    title = _get(job, "title") or "(untitled)"
    url = _get(job, "url") or ""
    etype = _get(job, "employment_type") or "—"
    salary = _get(job, "salary_text") or "—"
    posted = _get(job, "posted_at") or "?"
    keyword = _get(job, "matched_keyword") or "—"
    desc = (_get(job, "raw_description") or "").strip()

    subject = f"🆕 {title} [{etype}] — onlinejobs.ph"

    lines = [
        title,
        "",
        f"Type: {etype}    Salary: {salary}",
        f"Posted: {posted} UTC    Matched keyword: {keyword}",
        f"Apply: {url}",
    ]
    if hints:
        lines += ["", "📋 Application instructions detected — make sure you answer these:"]
        lines += [f"   • {h}" for h in hints]
    lines += [
        "",
        "─" * 30,
        "JOB DESCRIPTION",
        "─" * 30,
        desc or "(no description captured)",
        "",
        "— Caught by ApplyFirst",
    ]
    text = "\n".join(lines)

    esc = _html.escape
    hints_html = ""
    if hints:
        items = "".join(f"<li>{esc(h)}</li>" for h in hints)
        hints_html = (
            '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;'
            'padding:10px 14px;margin:12px 0"><strong>📋 Application instructions detected'
            f'</strong><ul style="margin:6px 0 0">{items}</ul></div>'
        )
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
