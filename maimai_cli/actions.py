from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import ACTIONS_FILE, ensure_config_dir
from .protocol import DEFAULT_ACTIONS


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_config_dir()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    try:
        path.chmod(0o600)
    except OSError:
        pass


class ActionRegistry:
    """Default + locally repaired Next server action id registry."""

    def __init__(self, path: Path = ACTIONS_FILE):
        self.path = path
        self._cache = _read_json(path)

    def get(self, key: str) -> str:
        override = self._cache.get("actions", {}).get(key)
        if isinstance(override, str) and override:
            return override
        return DEFAULT_ACTIONS[key]

    def remember_success(self, key: str, action_id: str, *, source: str = "runtime") -> None:
        if not key or not action_id:
            return
        actions = self._cache.setdefault("actions", {})
        if not isinstance(actions, dict):
            actions = {}
            self._cache["actions"] = actions
        actions[key] = action_id
        self._cache["updated_at"] = time.time()
        self._cache["source"] = source
        _write_json(self.path, self._cache)

    def candidates(self, key: str, discovered: list[str] | None = None) -> list[str]:
        ordered = [self.get(key), DEFAULT_ACTIONS.get(key, "")]
        ordered.extend(discovered or [])
        seen: set[str] = set()
        out: list[str] = []
        for action_id in ordered:
            if not action_id or action_id in seen:
                continue
            seen.add(action_id)
            out.append(action_id)
        return out
