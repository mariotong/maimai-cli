from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def extract_images(detail: dict) -> list[dict]:
    pics = detail.get("pics") if isinstance(detail, dict) else None
    if not isinstance(pics, list):
        return []

    images: list[dict] = []
    for index, pic in enumerate(pics, start=1):
        if not isinstance(pic, dict):
            continue
        original_url = pic.get("ourl") or pic.get("url")
        image_url = pic.get("url") or original_url
        if not original_url and not image_url:
            continue
        images.append({
            "index": index,
            "url": image_url,
            "thumbnail_url": pic.get("turl"),
            "origin_url": original_url,
            "width": pic.get("x"),
            "height": pic.get("y"),
            "origin_width": pic.get("ox"),
            "origin_height": pic.get("oy"),
            "origin_size": pic.get("osize"),
        })
    return images


def filename_for_image(kind: str, item_id: str, index: int, url: str, content_type: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix
    if not suffix:
        if "png" in content_type:
            suffix = ".png"
        elif "webp" in content_type:
            suffix = ".webp"
        else:
            suffix = ".jpg"
    return f"{kind}_{item_id}_{index:02d}{suffix}"
