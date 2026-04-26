from __future__ import annotations

import re


_SECRET_QUERY_RE = re.compile(
    r"(?i)\b(token|api[_-]?key|apikey|key|authorization|bot[_-]?token|chat[_-]?id)="
    r"([^&\s)'\")]+)"
)
_TELEGRAM_TOKEN_RE = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b")


def safe_error_message(error: BaseException | str, *, max_length: int = 160) -> str:
    if isinstance(error, BaseException):
        message = str(error) or error.__class__.__name__
    else:
        message = str(error)

    message = _SECRET_QUERY_RE.sub(lambda match: f"{match.group(1)}=<redacted>", message)
    message = _TELEGRAM_TOKEN_RE.sub("<redacted-telegram-token>", message)
    return message[:max_length]
