from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".maimai-cli"
COOKIE_FILE = CONFIG_DIR / "cookies.json"
REFS_FILE = CONFIG_DIR / "refs.json"
ACTIONS_FILE = CONFIG_DIR / "actions.json"


def ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def save_cookies(cookies: dict[str, str]) -> None:
    ensure_config_dir()
    payload: dict[str, Any] = {
        "saved_at": time.time(),
        "cookies": cookies,
    }
    COOKIE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    COOKIE_FILE.chmod(0o600)


def load_cookies() -> dict[str, str] | None:
    if not COOKIE_FILE.exists():
        return None
    try:
        payload = json.loads(COOKIE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    cookies = payload.get("cookies")
    if not isinstance(cookies, dict):
        return None
    return {str(k): str(v) for k, v in cookies.items() if v is not None}


def clear_cookies() -> None:
    if COOKIE_FILE.exists():
        COOKIE_FILE.unlink()


def cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items())
