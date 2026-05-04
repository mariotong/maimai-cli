from __future__ import annotations

import sys
from http.cookies import SimpleCookie

import click

from ..client import MaimaiClient
from ..config import clear_cookies, load_cookies, save_cookies
from ..errors import INVALID_ARGUMENT, MaimaiCliError
from ..output import emit_ok, structured_output_options
from .common import emit_exception


@click.command()
@structured_output_options
def status(as_json: bool, as_yaml: bool) -> None:
    """Show conservative login/session evidence."""
    cookies = load_cookies()
    if not cookies:
        emit_ok(
            {"authenticated": False, "message": "No saved cookies."},
            as_json=as_json, as_yaml=as_yaml,
        )
        return
    with MaimaiClient(cookies) as client:
        try:
            emit_ok(client.status_probe(), as_json=as_json, as_yaml=as_yaml)
        except Exception as exc:  # noqa: BLE001
            emit_exception(exc, as_json=as_json, as_yaml=as_yaml)
            raise SystemExit(1) from exc


@click.command("cookies")
@structured_output_options
def cookies_cmd(as_json: bool, as_yaml: bool) -> None:
    """Print saved cookie names only."""
    saved = load_cookies() or {}
    emit_ok(
        {"cookie_names": sorted(saved.keys())},
        as_json=as_json, as_yaml=as_yaml,
    )


@click.command()
@structured_output_options
def logout(as_json: bool, as_yaml: bool) -> None:
    """Delete saved local cookies."""
    clear_cookies()
    emit_ok({"logged_out": True}, as_json=as_json, as_yaml=as_yaml)


@click.command("import-cookie-header")
@click.option("--cookie", "cookie_header", envvar="MAIMAI_COOKIE", help="Raw Cookie header.")
@structured_output_options
def import_cookie_header(cookie_header: str | None, as_json: bool, as_yaml: bool) -> None:
    """Import a Cookie header from MAIMAI_COOKIE or --cookie."""
    if not cookie_header:
        if not sys.stdin.isatty():
            cookie_header = sys.stdin.read().strip()
    if not cookie_header:
        emit_exception(
            MaimaiCliError(
                INVALID_ARGUMENT,
                "Provide cookie via MAIMAI_COOKIE, --cookie, or stdin.",
            ),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)

    parsed = SimpleCookie()
    parsed.load(cookie_header)
    cookies = {key: morsel.value for key, morsel in parsed.items()}
    if not cookies:
        emit_exception(
            MaimaiCliError(INVALID_ARGUMENT, "No cookies parsed."),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)
    save_cookies(cookies)
    emit_ok(
        {"cookie_names": sorted(cookies.keys())},
        as_json=as_json, as_yaml=as_yaml,
    )


def register(cli: click.Group) -> None:
    cli.add_command(status)
    cli.add_command(cookies_cmd)
    cli.add_command(logout)
    cli.add_command(import_cookie_header)
