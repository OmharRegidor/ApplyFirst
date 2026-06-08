"""Notification channels (behind a small Notifier protocol)."""

from applyfirst.notify.compose import build_job_email
from applyfirst.notify.console import ConsoleNotifier
from applyfirst.notify.email_smtp import SmtpNotifier

__all__ = ["ConsoleNotifier", "SmtpNotifier", "build_job_email"]
