"""Structured logging setup for production observability (P1-16).

Configures JSON-line logging — one JSON object per log line — so
production log aggregators (ELK, Datadog, Loki) can parse them without
custom regex.  In development (ENV != production) plain-text logging
is used instead for readability.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exc"] = str(record.exc_info[1])
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """Wire up the root logger. Safe to call multiple times (idempotent)."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    env = os.getenv("ENV", "development")
    is_prod = env.lower() in ("prod", "production")

    handler = logging.StreamHandler(sys.stdout)
    if is_prod:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)-7s %(name)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root.setLevel(logging.INFO if is_prod else logging.DEBUG)
    root.addHandler(handler)

    # Keep noisy libs quiet
    for noisy in ("uvicorn.access", "httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name. Ensures setup is called first."""
    setup_logging()
    return logging.getLogger(name)
