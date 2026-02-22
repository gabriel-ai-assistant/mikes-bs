"""Structured JSON logging helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

_RESERVED_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonLogFormatter(logging.Formatter):
    """Render stdlib LogRecord objects as structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        event = record.getMessage()
        data = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_FIELDS and not key.startswith("_")
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        payload = {
            "timestamp": timestamp,
            "level": record.levelname.lower(),
            "module": record.name,
            "event": event,
            "data": data,
        }
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once to emit JSON records."""
    root = logging.getLogger()
    if getattr(root, "_openclaw_json_logging", False):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())

    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)
    root._openclaw_json_logging = True  # type: ignore[attr-defined]


def log_event(logger: logging.Logger, event: str, **data) -> None:
    """Emit structured event data under the standard schema."""
    logger.info(event, extra=data)
