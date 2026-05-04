from __future__ import annotations

from pathlib import Path

import click

from .. import refs
from ..errors import INVALID_ARGUMENT, NOT_FOUND, MaimaiCliError
from ..media import extract_images, filename_for_image
from ..output import emit_ok, structured_output_options
from ..protocol import BASE_URL
from .common import emit_exception, run_with_client


@click.command("images")
@click.argument("item_id")
@click.option("--kind", type=click.Choice(["feed", "gossip"]), default="gossip", show_default=True)
@click.option("--efid", default="", help="Required for feed images unless resolved via short index.")
@click.option("--egid", default="", help="Required for gossip images unless resolved via short index.")
@click.option("--download", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), help="Download images into this directory.")
@click.option("--thumb", is_flag=True, help="Use thumbnail URLs when downloading.")
@click.option("--raw", is_flag=True, help="Print full parsed image metadata.")
@structured_output_options
def images(
    item_id: str,
    kind: str,
    efid: str,
    egid: str,
    download: Path | None,
    thumb: bool,
    raw: bool,
    as_json: bool,
    as_yaml: bool,
) -> None:
    """List or download images attached to a visible feed/gossip item.

    ``item_id`` can be a 1-based short index from the most recent listing.
    """
    ref = refs.resolve_reference(item_id, expect_kind=kind)
    if not ref and item_id.isdigit():
        emit_exception(
            MaimaiCliError(
                NOT_FOUND,
                f"Short index {item_id} not found. Run a listing command first.",
            ),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)
    resolved_id = str(ref.get("id") or item_id)
    efid = efid or str(ref.get("efid") or "")
    egid = egid or str(ref.get("egid") or "")

    if kind == "feed" and not efid:
        emit_exception(
            MaimaiCliError(INVALID_ARGUMENT, "--efid is required for feed images"),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)
    if kind == "gossip" and not egid:
        emit_exception(
            MaimaiCliError(INVALID_ARGUMENT, "--egid is required for gossip images"),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)

    def action(client):
        detail = client.feed_detail(resolved_id, efid) if kind == "feed" else client.gossip_detail(resolved_id, egid)
        image_items = extract_images(detail)
        downloaded: list[dict] = []

        if download:
            download.mkdir(parents=True, exist_ok=True)
            referer = (
                f"{BASE_URL}/community/feed-detail/{resolved_id}"
                if kind == "feed"
                else f"{BASE_URL}/community/gossip-detail/{resolved_id}"
            )
            for image in image_items:
                url = image.get("thumbnail_url") if thumb else image.get("origin_url") or image.get("url")
                if not url:
                    continue
                resp = client.http.get(
                    url,
                    headers={
                        "referer": referer,
                        "accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    },
                )
                resp.raise_for_status()
                filename = filename_for_image(kind, resolved_id, int(image["index"]), url, resp.headers.get("content-type", ""))
                path = download / filename
                path.write_bytes(resp.content)
                downloaded.append({
                    "index": image["index"],
                    "path": str(path),
                    "bytes": len(resp.content),
                    "source": "thumbnail" if thumb else "origin",
                })

        return image_items, downloaded

    def on_success(result):
        image_items, downloaded = result
        emit_ok(
            {
                "images": image_items if raw else [
                    {
                        "index": image["index"],
                        "url": image.get("url"),
                        "thumbnail_url": image.get("thumbnail_url"),
                        "origin_url": image.get("origin_url"),
                        "size": {
                            "width": image.get("width"),
                            "height": image.get("height"),
                            "origin_width": image.get("origin_width"),
                            "origin_height": image.get("origin_height"),
                            "origin_size": image.get("origin_size"),
                        },
                    }
                    for image in image_items
                ],
                "downloaded": downloaded,
            },
            kind=kind,
            id=resolved_id,
            count=len(image_items),
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


def register(cli: click.Group) -> None:
    cli.add_command(images)
