"""Console notifier — prints the alert instead of sending it.

Used when email isn't configured, or with --preview, so you can see exactly what
would be emailed without sending anything.
"""

from __future__ import annotations


class ConsoleNotifier:
    def send(self, subject, text, html=None, attachments=None) -> None:
        print("\n" + "=" * 66)
        print("EMAIL PREVIEW (not sent)")
        print("Subject:", subject)
        if attachments:
            for name, data, _mime in attachments:
                print(f"Attachment: {name} ({len(data)} bytes)")
        print("-" * 66)
        print(text)
        print("=" * 66 + "\n")

    def describe(self) -> str:
        return "Console preview (set EMAIL_ENABLED=true + SMTP_* in .env to send for real)"
