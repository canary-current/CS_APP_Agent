"""
Clean stale cache and output files.

Usage:
  python clean.py           — clears cache/ and schools/
  python clean.py --cache   — clears cache/ only
  python clean.py --schools — clears schools/ only
"""

from __future__ import annotations
import argparse
import shutil
from pathlib import Path

_ROOT = Path(__file__).parent
_DIRS = {
    "cache":   _ROOT / "cache",
    "schools": _ROOT / "schools",
}


def _clear(name: str, path: Path) -> None:
    if not path.exists():
        print(f"  {name}/  — nothing to clear")
        return

    files = list(path.rglob("*"))
    file_count = sum(1 for f in files if f.is_file())

    shutil.rmtree(path)
    path.mkdir()

    print(f"  {name}/  — removed {file_count} file(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear cache and/or schools output.")
    parser.add_argument("--cache",   action="store_true", help="Clear cache/ only")
    parser.add_argument("--schools", action="store_true", help="Clear schools/ only")
    args = parser.parse_args()

    targets = []
    if args.cache:
        targets = ["cache"]
    elif args.schools:
        targets = ["schools"]
    else:
        targets = list(_DIRS)

    print("Clearing:")
    for name in targets:
        _clear(name, _DIRS[name])
    print("Done.")


if __name__ == "__main__":
    main()
