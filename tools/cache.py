import json
import hashlib
import time
from pathlib import Path

_CACHE_DIR = Path(__file__).parent.parent / "cache"
_TTL = 7 * 24 * 3600  # 7 days


def _path(key: str) -> Path:
    h = hashlib.sha256(key.encode()).hexdigest()
    return _CACHE_DIR / f"{h}.json"


def get_cached(key: str) -> dict | None:
    p = _path(key)
    if not p.exists():
        return None
    try:
        wrapper = json.loads(p.read_text())
        if "cached_at" in wrapper:
            if time.time() - wrapper["cached_at"] > _TTL:
                p.unlink()
                return None
            return wrapper["data"]
        # Legacy format without TTL wrapper — return as-is.
        return wrapper
    except Exception:
        return None


def set_cached(key: str, value: dict) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    _path(key).write_text(
        json.dumps({"cached_at": time.time(), "data": value}, indent=2, ensure_ascii=False)
    )
