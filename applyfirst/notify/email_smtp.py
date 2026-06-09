"""SMTP email notifier (works with Gmail app passwords; free).

Sends a multipart (plain + HTML) alert over SMTP-SSL, with optional file
attachments (e.g. the tailored resume PDF). For Gmail use smtp.gmail.com:465 with
an App Password (see .env.example).
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage


class SmtpNotifier:
    def __init__(self, host, port, user, password, sender, recipient) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender
        self.recipient = recipient

    def send(self, subject, text, html=None, attachments=None) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        for name, data, mimetype in attachments or []:
            maintype, _, subtype = mimetype.partition("/")
            msg.add_attachment(data, maintype=maintype or "application",
                               subtype=subtype or "octet-stream", filename=name)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30) as server:
            server.login(self.user, self.password)
            server.send_message(msg)

    def describe(self) -> str:
        return f"Email via {self.host} → {self.recipient}"
