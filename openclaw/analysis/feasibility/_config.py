from __future__ import annotations

import json
from pathlib import Path


def config_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "config"


def load_json(name: str) -> dict:
    path = config_dir() / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
