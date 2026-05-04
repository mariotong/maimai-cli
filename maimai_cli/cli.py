from __future__ import annotations

import click

from .commands import auth, content, media


@click.group()
def cli() -> None:
    """Personal-use Maimai CLI prototype."""


auth.register(cli)
content.register(cli)
media.register(cli)


if __name__ == "__main__":
    cli()
