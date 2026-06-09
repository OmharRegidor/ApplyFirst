"""The Notifier seam. V1 ships Console (preview) + Gmail SMTP.

Attachments are a list of (filename, data, mimetype) tuples, e.g.
("resume.pdf", b"...", "application/pdf").
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

Attachment = tuple[str, bytes, str]


@runtime_checkable
class Notifier(Protocol):
    def send(
        self,
        subject: str,
        text: str,
        html: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> None: ...

    def describe(self) -> str: ...
