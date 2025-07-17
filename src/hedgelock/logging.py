"""
Structured logging configuration using Loguru.
Provides consistent logging across all services with trace_id support.
"""

import json
import sys
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Optional

from loguru import logger

from src.hedgelock.config import settings

# Remove default handler
logger.remove()


def serialize(record: Dict[str, Any]) -> str:
    """Serialize log record to JSON format."""
    subset = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "service": settings.service_name,
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }

    # Add trace_id if present
    if "trace_id" in record["extra"]:
        subset["trace_id"] = record["extra"]["trace_id"]

    # Add any other extra fields
    for key, value in record["extra"].items():
        if key not in subset:
            subset[key] = value

    # Add exception info if present
    if record["exception"] is not None:
        subset["exception"] = {
            "type": record["exception"].type.__name__,
            "value": str(record["exception"].value),
            "traceback": record["exception"].traceback.raw,
        }

    return json.dumps(subset)


def format_text(record: Dict[str, Any]) -> str:
    """Format log record for text output."""
    format_string = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"

    # Add trace_id if present
    if "trace_id" in record["extra"]:
        format_string += " | <yellow>{extra[trace_id]}</yellow>"

    format_string += " - <level>{message}</level>\n"

    if record["exception"] is not None:
        format_string += "{exception}\n"

    return format_string


def configure_logging():
    """Configure logging based on settings."""
    # Configure output format
    if settings.monitoring.log_format == "json":
        logger.add(
            sys.stdout,
            format=serialize,
            level=settings.monitoring.log_level,
            backtrace=True,
            diagnose=True,
        )
    else:
        logger.add(
            sys.stdout,
            format=format_text,
            level=settings.monitoring.log_level,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    # Add file handler if configured
    if settings.monitoring.log_file:
        logger.add(
            settings.monitoring.log_file,
            format=serialize,
            level=settings.monitoring.log_level,
            rotation="100 MB",
            retention="7 days",
            compression="gz",
            backtrace=True,
            diagnose=True,
        )

    logger.info(
        "Logging configured",
        service=settings.service_name,
        environment=settings.environment,
        log_level=settings.monitoring.log_level,
        log_format=settings.monitoring.log_format,
    )


@contextmanager
def trace_context(trace_id: Optional[str] = None):
    """Context manager for adding trace_id to all logs within the context."""
    if trace_id is None:
        trace_id = str(uuid.uuid4())

    with logger.contextualize(trace_id=trace_id):
        yield trace_id


def get_logger(name: str) -> logger:
    """Get a logger instance with the given name."""
    return logger.bind(module=name)


# Configure logging on import
configure_logging()


# Export commonly used functions
__all__ = ["logger", "get_logger", "trace_context", "configure_logging"]
