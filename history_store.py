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


def load(device_id: str) -> dict[str, dict]:
    """Returns {key: {"history": [display lines], "records": [{"sender",
    "text", "sender_timestamp"}, ...]}}. Tolerates the pre-records format
    (a plain list of display lines per key) from before message records
    were persisted - those keys come back with an empty "records" list."""
    path = _path_for(device_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, dict] = {}
    for key, value in data.items():
        if isinstance(value, list):
            result[key] = {"history": value, "records": []}
        elif isinstance(value, dict):
            result[key] = {
                "history": value.get("history") or [],
                "records": value.get("records") or [],
            }
    return result


def save(device_id: str, chats: dict[str, dict]) -> None:
    path = _path_for(device_id)
    trimmed = {
        key: {
            "history": chat.get("history", [])[-MAX_MESSAGES:],
            "records": chat.get("records", [])[-MAX_MESSAGES:],
        }
        for key, chat in chats.items()
        if chat.get("history") or chat.get("records")
    }
    try:
        path.write_text(json.dumps(trimmed))
    except OSError:
        pass  # best-effort - a failed save shouldn't crash the chat session
