"""Error handling utilities — sanitize exception messages to prevent leaking sensitive data."""

import logging
import re

_logger = logging.getLogger(__name__)


class KelpMeshError(Exception):
    """Base exception for all kelpmesh errors."""

_SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE|"
    r"MERGE|COPY|GRANT|REVOKE|EXECUTE|CALL|WITH)\b",
    re.IGNORECASE,
)

_CREDENTIAL_URL = re.compile(
    r"(://)[^:@]+(:[^@]+)?@",
)

_ACCESS_TOKEN = re.compile(
    r"(?i)(token|password|secret|key|access_token|bearer)\s*[:=]\s*['\"][^'\"]+['\"]",
)

_KEY_LIKE = re.compile(
    r"[A-Za-z0-9+/=]{20,}(?:[.].*)?$",
)


def sanitize_exception_message(msg: str, max_length: int = 200) -> str:
    """Strip sensitive content from an exception message.

    Removes SQL queries, credential URLs, access tokens, and keys.
    Returns a safe, truncated description.
    """
    if not msg:
        return msg

    safe = msg

    # If message contains SQL keywords, keep only the first 60 chars as summary
    if _SQL_KEYWORDS.search(safe):
        summary = safe[:60].rstrip()
        safe = f"Query error: {summary}..."

    # Mask credentials in URLs (e.g., postgres://user:pass@host -> postgres://***@host)
    safe = _CREDENTIAL_URL.sub(r"\1***@", safe)

    # Mask inline tokens/passwords
    safe = _ACCESS_TOKEN.sub(r"\1 = [REDACTED]", safe)

    # Truncate long key-like strings that look like tokens
    lines = safe.split("\n")
    safe_lines = []
    for line in lines:
        if _KEY_LIKE.match(line.strip()):
            safe_lines.append("[REDACTED]")
        else:
            safe_lines.append(line)
    safe = "\n".join(safe_lines)

    if len(safe) > max_length:
        safe = safe[:max_length].rstrip() + "..."

    return safe


def sanitize_exception(e: Exception, max_length: int = 200) -> str:
    """Convert an exception to a safe, sanitized string for user-facing output."""
    msg = str(e)
    safe = sanitize_exception_message(msg, max_length=max_length)
    return f"{type(e).__name__}: {safe}"
