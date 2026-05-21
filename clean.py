"""
Clean stale cache and output files.

Usage:
  python clean.py           — clears cache/ and schools/
  python clean.py --cache   — clears cache/ only
  python clean.py --schools — clears schools/ only

Also exposes clear_dir() for in-process use (see agent.py /clear command).
"""

from __future__ import annotations
import argparse
import shutil
from pathlib import Path

_ROOT = Path(__file__).parent
CLEAR_DIRS: dict[str, Path] = {
    "cache":   _ROOT / "cache",
    "schools": _ROOT / "schools",
}


def clear_dir(path: Path) -> int:
    """
    Remove and re-create the directory. Returns the number of files removed,
    or -1 if the directory did not exist.
    """
    if not path.exists():
        return -1
    count = sum(1 for f in path.rglob("*") if f.is_file())
    shutil.rmtree(path)
    path.mkdir()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear cache and/or schools output.")
    parser.add_argument("--cache",   action="store_true", help="Clear cache/ only")
    parser.add_argument("--schools", action="store_true", help="Clear schools/ only")
    args = parser.parse_args()

    if args.cache:
        targets = ["cache"]
    elif args.schools:
        targets = ["schools"]
    else:
        targets = list(CLEAR_DIRS)

    print("Clearing:")
    for name in targets:
        count = clear_dir(CLEAR_DIRS[name])
        if count < 0:
            print(f"  {name}/  — nothing to clear")
        else:
            print(f"  {name}/  — removed {count} file(s)")
    print("Done.")


if __name__ == "__main__":
    main()
