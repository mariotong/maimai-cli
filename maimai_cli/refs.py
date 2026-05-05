"""Short-index references and context cache for list commands.

Inspired by xhs-cli: after running a listing command (feed / search / company-feed
/ comments / hot-rank), store the ordered items and any identifiers they carry
(efid / egid / trackable_token / mmid). Later commands (detail / comments /
profile / images) can reference them by 1-based short index instead of copying
the raw IDs.

Beyond the list index, we also keep a per-key context map so that even when a
user passes the raw id (not the short index), commands can still look up the
cached egid / efid / trackable_token from memory.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import ensure_config_dir

INDEX_FILE = Path.home() / ".maimai-cli" / "refs.json"
COMMENT_INDEX_FILE = Path.home() / ".maimai-cli" / "comment_refs.json"
CONTEXT_FILE = Path.home() / ".maimai-cli" / "context.json"

_INDEX_TTL_SECONDS = 24 * 3600
_CONTEXT_TTL_SECONDS = 7 * 24 * 3600
_CONTEXT_MAX_ENTRIES = 500
_INDEX_FILES = {
    "default": INDEX_FILE,
    "comments": COMMENT_INDEX_FILE,
}


def _index_file(scope: str = "default") -> Path:
    return _INDEX_FILES.get(scope, INDEX_FILE)


def _write_json(path: Path, payload: Any) -> None:
    ensure_config_dir()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_entry(entry: dict) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    kind = str(entry.get("kind") or "").strip()
    item_id = str(entry.get("id") or "").strip()
    if not kind or not item_id:
        return None
    out: dict[str, Any] = {"kind": kind, "id": item_id}
    for key in ("efid", "egid", "trackable_token", "mmid", "webcid", "cid"):
        value = entry.get(key)
        if value:
            out[key] = str(value)
    label = entry.get("label")
    if label:
        out["label"] = str(label)[:120]
    return out


def save_index(entries: list[dict], *, source_command: str, scope: str = "default") -> list[dict]:
    """Persist the ordered list produced by a listing command."""
    normalized = [e for e in (_normalize_entry(item) for item in entries) if e]
    payload = {
        "saved_at": time.time(),
        "source_command": source_command,
        "entries": normalized,
    }
    _write_json(_index_file(scope), payload)
    # Mirror each entry into the context cache keyed by (kind,id) so that
    # lookups by raw id also benefit.
    for entry in normalized:
        cache_context(entry["kind"], entry["id"], entry)
    return normalized


def load_index(scope: str = "default") -> dict[str, Any]:
    data = _read_json(_index_file(scope))
    if not isinstance(data, dict):
        return {"entries": [], "saved_at": 0, "source_command": ""}
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    return {
        "entries": [e for e in (_normalize_entry(item) for item in entries) if e],
        "saved_at": float(data.get("saved_at") or 0),
        "source_command": str(data.get("source_command") or ""),
    }


def get_by_short_index(short_index: int, *, scope: str = "default") -> dict[str, Any] | None:
    if short_index <= 0:
        return None
    index = load_index(scope)
    if time.time() - index["saved_at"] > _INDEX_TTL_SECONDS:
        return None
    entries = index["entries"]
    if short_index > len(entries):
        return None
    return entries[short_index - 1]


def resolve_reference(token: str, *, expect_kind: str | None = None, scope: str = "default") -> dict[str, Any]:
    """Resolve a user-supplied token.

    - Pure digits → try to look it up in the short-index cache first.
    - Otherwise return a stub dict with the raw id under ``id`` and any cached
      context merged in.
    """
    token = (token or "").strip()
    if not token:
        return {}

    if token.isdigit():
        entry = get_by_short_index(int(token), scope=scope)
        if entry is not None:
            if expect_kind and entry.get("kind") != expect_kind:
                # When the user disagrees with the cached kind, fall through
                # and treat the digits as a raw id, while still allowing the
                # raw-id context cache to supply egid / efid below.
                pass
            else:
                return dict(entry)

    cached = get_context(expect_kind or "", token) if expect_kind else {}
    if cached:
        merged = dict(cached)
        merged["id"] = token
        return merged
    return {"id": token}


# ─── Context cache (kind,id → egid/efid/trackable_token/...) ──────────────


def _load_context() -> dict[str, Any]:
    data = _read_json(CONTEXT_FILE)
    if not isinstance(data, dict):
        return {}
    return data


def _prune_context(cache: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    fresh = {
        key: value
        for key, value in cache.items()
        if isinstance(value, dict)
        and now - float(value.get("ts") or 0) <= _CONTEXT_TTL_SECONDS
    }
    if len(fresh) <= _CONTEXT_MAX_ENTRIES:
        return fresh
    # Drop oldest entries first.
    ordered = sorted(fresh.items(), key=lambda kv: float(kv[1].get("ts") or 0))
    return dict(ordered[-_CONTEXT_MAX_ENTRIES:])


def _context_key(kind: str, item_id: str) -> str:
    return f"{kind}:{item_id}"


def cache_context(kind: str, item_id: str, entry: dict[str, Any]) -> None:
    if not kind or not item_id:
        return
    cache = _load_context()
    existing = cache.get(_context_key(kind, item_id), {})
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in entry.items():
        if value:
            merged[key] = value
    merged["ts"] = time.time()
    cache[_context_key(kind, item_id)] = merged
    _write_json(CONTEXT_FILE, _prune_context(cache))


def get_context(kind: str, item_id: str) -> dict[str, Any]:
    if not kind or not item_id:
        return {}
    entry = _load_context().get(_context_key(kind, item_id))
    if not isinstance(entry, dict):
        return {}
    if time.time() - float(entry.get("ts") or 0) > _CONTEXT_TTL_SECONDS:
        return {}
    return {k: v for k, v in entry.items() if k != "ts"}


def clear_all() -> None:
    for path in (INDEX_FILE, COMMENT_INDEX_FILE, CONTEXT_FILE):
        if path.exists():
            path.unlink()
