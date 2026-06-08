"""The Notifier seam. V1 ships Console (preview) + Gmail SMTP."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    def send(self, subject: str, text: str, html: str | None = None) -> None: ...

    def describe(self) -> str: ...
