"""Opt-in structured (JSON) logging.

By default this is a no-op: the package logger carries a NullHandler, so existing
human-readable ``print()`` output on stdout is untouched. When ``APPLYFIRST_LOG_JSON``
is enabled (via ``configure``), structured events are written as one JSON object per
line to **stderr** — keeping machine logs separate from the human console on stdout,
so ``python -m applyfirst.cli run 2>run.jsonl`` captures a clean event stream.

Usage:
    from applyfirst import log
    LOG = log.get_logger("pipeline")
    log.event(LOG, "cycle_complete", new=2, emailed=1)
"""

from __future__ import annotations

import json
import logging
import sys

_ROOT_NAME = "applyfirst"
_root = logging.getLogger(_ROOT_NAME)
_root.addHandler(logging.NullHandler())  # silence "no handlers" until configured

_configured = False


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single-line JSON object.

    The log *message* is the event name; structured fields ride on
    ``record.fields`` (a dict) and are merged into the top-level object.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure(json_enabled: bool = False, level: str = "INFO") -> None:
    """Enable JSON logging to stderr. No-op when disabled or already configured."""
    global _configured
    if not json_enabled or _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    _root.addHandler(handler)
    _root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    _root.propagate = False
    _configured = True


def get_logger(suffix: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{_ROOT_NAME}.{suffix}" if suffix else _ROOT_NAME)


def event(logger: logging.Logger, name: str, level: int = logging.INFO,
          exc_info: bool = False, **fields) -> None:
    """Log a structured event. A no-op (no output) unless ``configure`` ran."""
    logger.log(level, name, extra={"fields": fields}, exc_info=exc_info)
