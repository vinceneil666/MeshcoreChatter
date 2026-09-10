"""Per-device chat history persistence.

History is keyed by the connected node's own public key, not the serial port
or BLE address, so it follows the physical device across USB ports / BLE vs
serial, and stays separate if you ever talk to a different node.
"""
from __future__ import annotations

import json
from pathlib import Path

HISTORY_DIR = Path.home() / ".meshcore-chat" / "history"
MAX_MESSAGES = 50


def _path_for(device_id: str) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in device_id) or "unknown"
    return HISTORY_DIR / f"{safe}.json"


def load(device_id: str) -> dict[str, list[str]]:
    path = _path_for(device_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save(device_id: str, history: dict[str, list[str]]) -> None:
    path = _path_for(device_id)
    trimmed = {key: lines[-MAX_MESSAGES:] for key, lines in history.items() if lines}
    try:
        path.write_text(json.dumps(trimmed))
    except OSError:
        pass  # best-effort - a failed save shouldn't crash the chat session
