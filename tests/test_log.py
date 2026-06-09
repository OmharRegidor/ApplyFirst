"""Tests for opt-in structured JSON logging."""

from __future__ import annotations

import json
import logging

from applyfirst.log import JsonFormatter, event, get_logger


def test_json_formatter_emits_valid_json_with_fields():
    rec = logging.LogRecord("applyfirst.pipeline", logging.INFO,
                            __file__, 1, "cycle_complete", None, None)
    rec.fields = {"new": 2, "emailed": 1}
    data = json.loads(JsonFormatter().format(rec))
    assert data["event"] == "cycle_complete"
    assert data["level"] == "INFO"
    assert data["logger"] == "applyfirst.pipeline"
    assert data["new"] == 2 and data["emailed"] == 1
    assert "ts" in data


def test_json_formatter_includes_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord("applyfirst", logging.ERROR, __file__, 1,
                                "email_failed", None, sys.exc_info())
    data = json.loads(JsonFormatter().format(rec))
    assert "boom" in data["error"]


def test_get_logger_namespacing():
    assert get_logger().name == "applyfirst"
    assert get_logger("backup").name == "applyfirst.backup"


def test_event_is_noop_when_unconfigured():
    # With only the NullHandler attached, emitting must not raise or print.
    event(get_logger("test"), "hello", x=1)
