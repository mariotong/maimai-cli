from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import click

from ..client import MaimaiClient
from ..config import load_cookies
from ..errors import (
    NOT_AUTHENTICATED,
    UNKNOWN_ERROR,
    MaimaiCliError,
    error_code_for_exception,
)
from ..output import emit_err

T = TypeVar("T")


def require_client(fn: Callable[[MaimaiClient], T]) -> T:
    """Legacy entry point — raises MaimaiCliError when not authenticated."""
    cookies = load_cookies()
    if not cookies:
        raise MaimaiCliError(
            NOT_AUTHENTICATED,
            "No saved cookies. Import a Cookie header with `maimai import-cookie-header`.",
        )
    with MaimaiClient(cookies) as client:
        return fn(client)


def run_with_client(
    action: Callable[[MaimaiClient], T],
    *,
    as_json: bool = False,
    as_yaml: bool = False,
    on_success: Callable[[T], None] | None = None,
) -> T | None:
    """Run ``action`` with an authenticated client and centralize error emission.

    ``on_success`` is called with the result when the action succeeds. If it is
    not provided the caller is expected to emit output itself — this lets
    complex commands shape their own payload.
    """
    try:
        result = require_client(action)
    except click.UsageError:
        raise
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize to stable codes
        code = error_code_for_exception(exc)
        message = str(exc) if not isinstance(exc, MaimaiCliError) else exc.message
        emit_err(code, message, as_json=as_json, as_yaml=as_yaml)
        raise SystemExit(1) from exc
    if on_success is not None:
        on_success(result)
    return result


def emit_exception(
    exc: BaseException,
    *,
    as_json: bool = False,
    as_yaml: bool = False,
) -> None:
    """Shared helper for non-client commands (e.g. auth) to emit errors."""
    code = error_code_for_exception(exc) if not isinstance(exc, MaimaiCliError) else exc.code
    if isinstance(exc, MaimaiCliError):
        message = exc.message
    else:
        message = str(exc) or UNKNOWN_ERROR
    emit_err(code, message, as_json=as_json, as_yaml=as_yaml)
