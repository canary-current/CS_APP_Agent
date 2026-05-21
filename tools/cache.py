import json
import hashlib
from pathlib import Path

_CACHE_DIR = Path(__file__).parent.parent / "cache"


def _path(key: str) -> Path:
    h = hashlib.sha256(key.encode()).hexdigest()[:20]
    return _CACHE_DIR / f"{h}.json"


def get_cached(key: str) -> dict | None:
    p = _path(key)
    if p.exists():
        return json.loads(p.read_text())
    return None


def set_cached(key: str, value: dict) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    _path(key).write_text(json.dumps(value, indent=2, ensure_ascii=False))
