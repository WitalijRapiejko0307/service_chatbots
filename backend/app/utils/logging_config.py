"""Structured logging configuration."""

import json
import logging
import re
import sys
from datetime import datetime
from typing import Any, Optional

from app.utils.datetime_utils import to_utc_iso_string, utc_now

# Query/body keys (and similar) whose values must never appear in logs.
_SECRET_KEY_RE = re.compile(
    r"(token|secret|code|password|authorization|access_token)",
    re.IGNORECASE,
)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)(token|secret|code|password|authorization|access_token)\s*[=:]\s*[^\s&\"']+"
)
_TELEGRAM_BOT_TOKEN_RE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+=/]+")


def redact_secrets(text: str) -> str:
    """Mask tokens, OAuth codes, and password-like values in a log string."""
    if not text:
        return text
    out = _TELEGRAM_BOT_TOKEN_RE.sub("***REDACTED_BOT_TOKEN***", text)
    out = _BEARER_RE.sub("Bearer ***", out)
    out = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}=***", out)
    return out


def is_secret_query_key(key: str) -> bool:
    """True when a query parameter name looks like a secret."""
    return bool(_SECRET_KEY_RE.search(key or ""))


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": to_utc_iso_string(utc_now()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields from record attributes (passed via extra parameter)
        # Note: extra fields are already in record.__dict__, we check for common ones
        for key in ["request_id", "client_ip", "path", "method", "status_code", "process_time"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Setup application logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set levels for third-party loggers
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter with request ID support."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Process log message with extra context."""
        extra = kwargs.setdefault("extra", {})
        if "request_id" in self.extra:
            extra["request_id"] = self.extra["request_id"]
        return msg, kwargs

