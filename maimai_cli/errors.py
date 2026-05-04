"""Stable error-code mapping for structured CLI output.

Inspired by xhs-cli. Commands should map any raised exception into one of a
small set of stable string codes so that consumers (humans or scripts) can
branch on the error without parsing free-form messages.
"""

from __future__ import annotations

import httpx
import click

from .client import MaimaiError

# Canonical codes — keep this list intentionally small and stable.
NOT_AUTHENTICATED = "not_authenticated"
SESSION_EXPIRED = "session_expired"
HTTP_ERROR = "http_error"
PARSE_ERROR = "parse_error"
INVALID_ARGUMENT = "invalid_argument"
NOT_FOUND = "not_found"
PAGINATION_UNSUPPORTED = "pagination_unsupported"
UNKNOWN_ERROR = "unknown_error"


class MaimaiCliError(Exception):
    """Exception carrying a stable error code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def error_code_for_exception(exc: BaseException) -> str:
    if isinstance(exc, MaimaiCliError):
        return exc.code
    if isinstance(exc, click.UsageError):
        return INVALID_ARGUMENT
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        if status in (401, 403):
            return NOT_AUTHENTICATED
        if status == 404:
            return NOT_FOUND
        return HTTP_ERROR
    if isinstance(exc, httpx.HTTPError):
        return HTTP_ERROR
    if isinstance(exc, MaimaiError):
        message = str(exc).lower()
        if "http 401" in message or "http 403" in message:
            return NOT_AUTHENTICATED
        if message.startswith("http "):
            return HTTP_ERROR
        if "could not parse" in message or "non-json" in message:
            return PARSE_ERROR
        if "no saved cookies" in message:
            return NOT_AUTHENTICATED
        return UNKNOWN_ERROR
    return UNKNOWN_ERROR
